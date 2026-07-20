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

DNS_TEST = "microk8s kubectl run -it --rm debug --image=busybox:1.28.4 --restart=Never -- nslookup google.com"


def test_core_dns(juju: jubilant.Juju, charm_config: dict):
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
    with microk8s_kubernetes_cloud_and_model(juju, "microk8s") as (k8s_juju, model_name):
        LOG.info("Deploy CoreDNS")
        k8s_juju.deploy(
            config.MK8S_COREDNS_CHARM,
            app="coredns",
            channel=config.MK8S_COREDNS_CHANNEL,
            trust=True,
        )
        wait_for_apps(k8s_juju, ["coredns"])

        LOG.info("Create offer for coredns:dns-provider endpoint")
        k8s_juju.offer("coredns", endpoint="dns-provider", name="coredns")

        try:
            LOG.info("Consume coredns:dns-provider and relate with microk8s")
            juju.consume(f"{model_name}.coredns", "coredns", owner="admin")
            juju.integrate("microk8s", "coredns")
            wait_for_apps(juju, ["microk8s"])

            wait_for_apps(k8s_juju, ["coredns"])

            for _ in range(10):
                rc, stdout, stderr = run_unit(juju, unit, DNS_TEST)
                LOG.info("Verify the pod dns resolution %s", (rc, stdout, stderr))
                if rc == 0:
                    break

            assert rc == 0, "Failed to resolve DNS in 10 tries"

        finally:
            juju.remove_relation("microk8s:dns", "coredns", force=True)
            juju.cli("remove-saas", "coredns")
            wait_for_apps(juju, ["microk8s"])
