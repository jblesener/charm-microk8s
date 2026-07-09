#!/usr/bin/env python3
#
# Copyright 2023 Canonical, Ltd.
#

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


def test_metallb_traefik(juju: jubilant.Juju, charm_config: dict):
    # deploy microk8s
    if "microk8s" not in juju.status().apps:
        deploy_microk8s(
            juju,
            app="microk8s",
            charm_config=charm_config,
            extra_config={"hostpath_storage": True},
        )
        wait_for_apps(juju, ["microk8s"], timeout=20 * 60)

    unit = get_unit_name(juju, "microk8s")

    # bootstrap a juju cloud on the deployed microk8s
    with microk8s_kubernetes_cloud_and_model(juju, "microk8s") as (k8s_juju, ns):
        LOG.info("Deploy MetalLB")
        k8s_juju.deploy(
            config.MK8S_METALLB_CHARM,
            app="metallb",
            config={"iprange": "10.42.42.42-10.42.42.42"},
            channel=config.MK8S_METALLB_CHANNEL,
        )
        wait_for_apps(k8s_juju, ["metallb"])
        LOG.info("Deploy Traefik")
        k8s_juju.deploy(
            config.MK8S_TRAEFIK_K8S_CHARM,
            app="traefik",
            channel=config.MK8S_TRAEFIK_K8S_CHANNEL,
            trust=True,
        )
        LOG.info("Deploy hello kubecon")
        k8s_juju.deploy(
            config.MK8S_HELLO_KUBECON_CHARM,
            app="hello-kubecon",
            channel=config.MK8S_HELLO_KUBECON_CHANNEL,
        )
        wait_for_apps(k8s_juju, ["traefik", "hello-kubecon"])
        k8s_juju.integrate("traefik", "hello-kubecon")

        stdout = ""
        while "10.42.42.42" not in stdout:
            rc, stdout, stderr = run_unit(juju, unit, f"microk8s kubectl get svc traefik -n {ns}")
            LOG.info("Check LoadBalancer service %s on %s", (rc, stdout, stderr), ns)

        # Make sure hello-kubecon is available from ingress
        while "Hello, Kubecon" not in stdout:
            rc, stdout, stderr = run_unit(
                juju, unit, f"curl http://10.42.42.42:80/{ns}-hello-kubecon"
            )
            LOG.info("Waiting for hello kubecon message %s", (rc, stderr))
