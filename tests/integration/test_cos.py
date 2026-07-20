#!/usr/bin/env python3
#
# Copyright 2023 Canonical, Ltd.
#

import json
import logging

import config
import jubilant

from conftest import (
    deploy_microk8s,
    get_unit_name,
    microk8s_kubernetes_cloud_and_model,
    run_unit,
    wait_for_apps,
)

LOG = logging.getLogger(__name__)


def test_cos(juju: jubilant.Juju, charm_config: dict):
    # deploy microk8s
    if "microk8s" not in juju.status().apps:
        deploy_microk8s(
            juju,
            app="microk8s",
            charm_config=charm_config,
            extra_config={"hostpath_storage": True},
            # NOTE(neoaggelos/2023-09-17): grafana-agent needs libssl.so.3.
            series="jammy",
        )
        wait_for_apps(juju, ["microk8s"], timeout=20 * 60)

    if "grafana-agent" not in juju.status().apps:
        juju.deploy(
            config.MK8S_GRAFANA_AGENT_CHARM,
            channel=config.MK8S_GRAFANA_AGENT_CHANNEL,
            app="grafana-agent",
        )
        juju.integrate("microk8s", "grafana-agent")
        wait_for_apps(juju, ["microk8s", "grafana-agent"], raise_on_error=False)

    microk8s_unit = get_unit_name(juju, "microk8s")

    # bootstrap a juju cloud on the deployed microk8s
    with microk8s_kubernetes_cloud_and_model(juju, "microk8s") as (k8s_juju, k8s_model_name):
        LOG.info("Deploy MetalLB")
        k8s_juju.deploy(
            config.MK8S_METALLB_CHARM,
            app="metallb",
            config={"iprange": "10.42.42.42-10.42.42.42"},
            channel=config.MK8S_METALLB_CHANNEL,
        )
        wait_for_apps(k8s_juju, ["metallb"])

        LOG.info("Deploy cos-lite")
        k8s_juju.deploy(
            config.MK8S_COS_BUNDLE,
            channel=config.MK8S_COS_CHANNEL,
            trust=True,
        )
        wait_for_apps(k8s_juju, ["prometheus"], timeout=30 * 60)

        LOG.info("Create offers for cos-lite endpoints")
        k8s_juju.offer("prometheus", endpoint="receive-remote-write", name="prometheus")
        k8s_juju.offer("loki", endpoint="logging", name="loki")
        k8s_juju.offer("grafana", endpoint="grafana-dashboard", name="grafana")

        try:
            LOG.info("Consume cos-lite and relate with grafana-agent")
            juju.consume(f"{k8s_model_name}.prometheus", "prometheus", owner="admin")
            juju.consume(f"{k8s_model_name}.loki", "loki", owner="admin")
            juju.consume(f"{k8s_model_name}.grafana", "grafana", owner="admin")
            juju.integrate("grafana-agent", "prometheus")
            juju.integrate("grafana-agent", "loki")
            juju.integrate("grafana-agent", "grafana")

            wait_for_apps(juju, ["microk8s", "grafana-agent"], timeout=20 * 60)

            rc, hostname, stderr = run_unit(juju, microk8s_unit, "hostname")
            assert rc == 0, f"failed to retrieve unit hostname: {stderr}"
            hostname = hostname.strip()
            for query in [
                'up{job="kubelet", node="%s", metrics_path="/metrics"} > 0' % hostname,
                'up{job="kubelet", node="%s", metrics_path="/metrics/cadvisor"} > 0' % hostname,
                'up{job="kubelet", node="%s", metrics_path="/metrics/probes"} > 0' % hostname,
                'up{job="apiserver"} > 0',
                'up{job="kube-controller-manager"} > 0',
                'up{job="kube-scheduler"} > 0',
                'up{job="kube-proxy"} > 0',
                'up{job="kube-state-metrics"} > 0',
            ]:
                while True:
                    try:
                        rc, stdout, stderr = run_unit(
                            juju,
                            microk8s_unit,
                            f"""
                            curl --silent \
                                http://10.42.42.42/{k8s_model_name}-prometheus-0/api/v1/query \
                                --data-urlencode query='{query}'
                            """,
                        )
                        if rc != 0:
                            raise ValueError("failed to query")

                        response = json.loads(stdout)
                        if response["status"] != "success":
                            raise ValueError("query not successful")
                        if not response["data"]["result"]:
                            raise ValueError("no data yet")

                        LOG.info("Validated query %s", query)
                        break

                    except (ValueError, json.JSONDecodeError, KeyError) as exc:
                        LOG.warning("%s failed: %s\ncurl: %s", query, exc, (rc, stdout, stderr))

            LOG.info("Success! Starting teardown of the environment")

        finally:
            juju.remove_relation("grafana-agent:grafana-dashboards-provider", "grafana", force=True)
            juju.remove_relation("grafana-agent:send-remote-write", "prometheus", force=True)
            juju.remove_relation("grafana-agent:logging-consumer", "loki", force=True)
            wait_for_apps(juju, ["grafana-agent"])

            juju.cli("remove-saas", "prometheus")
            juju.cli("remove-saas", "loki")
            juju.cli("remove-saas", "grafana")
            wait_for_apps(juju, ["grafana-agent"])
