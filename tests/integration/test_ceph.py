#!/usr/bin/env python3
#
# Copyright 2023 Canonical, Ltd.
#
import logging

import config
import jubilant
import pytest
from conftest import (
    available_cloud_types,
    deploy_microk8s,
    get_unit_name,
    run_unit,
    wait_for_apps,
)

LOG = logging.getLogger(__name__)


def test_ceph_csi(juju: jubilant.Juju, charm_config: dict):
    """Integration test for MicroK8s with Ceph CSI operator"""

    if available_cloud_types(juju) == {"lxd"}:
        pytest.skip("Ceph CSI test not supported on LXD cloud, skipping")

    LOG.info("Deploy MicroK8s")
    if "microk8s" not in juju.status().apps:
        deploy_microk8s(juju, app="microk8s", charm_config=charm_config)
        wait_for_apps(juju, ["microk8s"])

    # deploy ceph
    LOG.info("Deploy Ceph")
    if "ceph-mon" not in juju.status().apps:
        juju.deploy(
            config.MK8S_CEPH_MON_CHARM,
            app="ceph-mon",
            channel=config.MK8S_CEPH_MON_CHANNEL,
            config={"monitor-count": 1},
        )
    if "ceph-osd" not in juju.status().apps:
        juju.deploy(
            config.MK8S_CEPH_OSD_CHARM,
            app="ceph-osd",
            channel=config.MK8S_CEPH_OSD_CHANNEL,
            storage={"osd-devices": "5G,3"},
            num_units=3,
        )
        juju.integrate("ceph-mon", "ceph-osd")
    wait_for_apps(juju, ["ceph-mon", "ceph-osd"])

    LOG.info("Deploy Ceph CSI operator")
    if "ceph-csi" not in juju.status().apps:
        juju.deploy(
            config.MK8S_CEPH_CSI_CHARM,
            app="ceph-csi",
            channel=config.MK8S_CEPH_CSI_CHANNEL,
        )
        juju.integrate("ceph-mon", "ceph-csi")
        juju.integrate("microk8s:kubernetes-info", "ceph-csi:kubernetes-info")

    wait_for_apps(juju, ["microk8s", "ceph-csi"])

    unit = get_unit_name(juju, "microk8s")
    for attempt in range(10):
        _, stdout, _ = run_unit(juju, unit, "microk8s kubectl get storageclass")
        LOG.info("(attempt %d) Waiting for Ceph StorageClass to appear", attempt)

        if "ceph-ext4" in stdout and "ceph-xfs" in stdout:
            break

    assert "ceph-ext4" in stdout, "Ceph StorageClasses were not created in time"
