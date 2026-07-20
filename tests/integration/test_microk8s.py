#!/usr/bin/env python3
#
# Copyright 2023 Canonical, Ltd.
#

import config
import jubilant
import pytest

from conftest import deploy_microk8s, get_unit_name, run_unit, wait_for_apps


@pytest.mark.parametrize("cp_units, worker_units", config.MK8S_CLUSTER_SIZES)
@pytest.mark.parametrize("series", config.MK8S_SERIES)
def test_microk8s_cluster(
    juju: jubilant.Juju, charm_config: dict, series: str, cp_units: int, worker_units: int
):
    """Deploy a cluster, configure RBAC, wait for units to come up"""

    application_name = f"microk8s-{series or 'default'}-{cp_units}c{worker_units}w"

    apps = [application_name]
    deploy_microk8s(
        juju,
        app=application_name,
        num_units=cp_units,
        charm_config=charm_config,
        series=series,
    )

    wait_for_apps(juju, [application_name], timeout=60 * 60)

    unit = get_unit_name(juju, application_name)

    # When rbac is not enabled, we can't query for `system:node` cluster role
    rc, stdout, stderr = run_unit(juju, unit, "microk8s kubectl get clusterrole system:node")
    assert rc == 1, f"system:node should be missing with RBAC disabled {stdout=}, {stderr=}"

    wait_for_apps(juju, [application_name], timeout=60 * 60)

    # When rbac is enabled via configs, we can get `system:node` clusterrole successfully
    juju.config(application_name, {"rbac": True})

    wait_for_apps(juju, [application_name], timeout=60 * 60)

    if worker_units > 0:
        worker_app = f"{application_name}-worker"
        apps.append(worker_app)
        deploy_microk8s(
            juju,
            app=worker_app,
            num_units=worker_units,
            charm_config={"role": "worker", **charm_config},
            series=series,
        )

        juju.integrate(f"{application_name}:workers", f"{worker_app}:control-plane")

        wait_for_apps(juju, [worker_app], timeout=60 * 60)

    wait_for_apps(juju, [application_name], timeout=60 * 60)

    # When rbac is enabled, we can get `system:node` clusterrole successfully
    rc, stdout, stderr = run_unit(juju, unit, "microk8s kubectl get clusterrole system:node")
    assert rc == 0, f"system:node should be present with RBAC enabled {stdout=} {stderr=}"

    wait_for_apps(juju, apps, timeout=60 * 60)
    for app in apps:
        juju.remove_application(app, force=True)
