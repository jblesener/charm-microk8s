#
# Copyright 2023 Canonical, Ltd.
#
import json
import logging
import pathlib
import subprocess
import uuid
from contextlib import contextmanager
from typing import Generator, Set, Tuple

import config
import jubilant
import pytest

LOG = logging.getLogger(__name__)

SERIES_BASES = {
    "jammy": "ubuntu@22.04",
    "noble": "ubuntu@24.04",
    "resolute": "ubuntu@26.04",
}


def _build_charm() -> str:
    subprocess.run(["charmcraft", "pack", "-v"], check=True)
    charms = sorted(pathlib.Path(".").glob("microk8s-ng*.charm"))
    if not charms:
        raise FileNotFoundError("charmcraft did not produce a microk8s-ng charm")
    return f"./{charms[-1]}"


def _constraints(value: str) -> dict[str, str]:
    return dict(item.split("=", 1) for item in value.split()) if value else {}


def base_for_series(series: str) -> str | None:
    if not series:
        return None
    return SERIES_BASES[series]


def deploy_microk8s(
    juju: jubilant.Juju,
    *,
    app: str,
    charm_config: dict,
    num_units: int = 1,
    series: str = "",
    extra_config: dict | None = None,
):
    deploy_config = {**charm_config}
    if extra_config:
        deploy_config.update(extra_config)

    juju.deploy(
        config.MK8S_CHARM,
        app=app,
        num_units=num_units,
        config=deploy_config,
        channel=config.MK8S_CHARM_CHANNEL or None,
        base=base_for_series(series),
        constraints=_constraints(config.MK8S_CONSTRAINTS),
    )


def wait_for_apps(
    juju: jubilant.Juju,
    apps: list[str],
    *,
    timeout: int = 20 * 60,
    raise_on_error: bool = True,
):
    error = jubilant.any_error if raise_on_error else None
    return juju.wait(
        lambda status: jubilant.all_active(status, *apps),
        error=error,
        timeout=timeout,
    )


def get_unit_name(juju: jubilant.Juju, app: str) -> str:
    units = juju.status().apps[app].units
    if not units:
        raise ValueError(f"application {app!r} has no units")
    return sorted(units)[0]


def model_config() -> dict:
    values = {"logging-config": "<root>=INFO;unit=DEBUG"}
    if config.MK8S_PROXY is not None:
        values["http-proxy"] = config.MK8S_PROXY
        values["https-proxy"] = config.MK8S_PROXY
        values["ftp-proxy"] = config.MK8S_PROXY
    if config.MK8S_NO_PROXY is not None:
        values["no-proxy"] = config.MK8S_NO_PROXY
    return values


@pytest.fixture(scope="module")
def juju(request) -> Generator[jubilant.Juju, None, None]:
    """Set up a Jubilant client for either an existing model or a temporary model."""

    if config.MK8S_CHARM == "build":
        config.MK8S_CHARM = _build_charm()

    model = request.config.getoption("--model")
    if model:
        client = jubilant.Juju(model=model)
        client.model_config(model_config())
        yield client
        return

    with jubilant.temp_model() as client:
        client.model_config(model_config())
        yield client


@pytest.fixture(scope="module")
def charm_config():
    """Fixture with common MicroK8s charm configuration settings."""
    charm_config = {}
    if config.MK8S_SNAP_CHANNEL:
        charm_config["channel"] = config.MK8S_SNAP_CHANNEL
    if config.MK8S_PROXY is not None:
        charm_config["containerd_http_proxy"] = config.MK8S_PROXY
        charm_config["containerd_https_proxy"] = config.MK8S_PROXY
    if config.MK8S_NO_PROXY is not None:
        charm_config["containerd_no_proxy"] = config.MK8S_NO_PROXY

    yield charm_config


def run_unit(juju: jubilant.Juju, unit: str, command: str) -> Tuple[int, str, str]:
    """Execute a command on the specified unit and return exit code, stdout, and stderr."""

    try:
        task = juju.exec(command, unit=unit, wait=10 * 60)
    except jubilant.TaskError as exc:
        task = exc.task
    return task.return_code, task.stdout, task.stderr


def available_cloud_types(juju: jubilant.Juju) -> Set[str]:
    """Return all cloud types available on the current controller."""

    controllers = json.loads(juju.cli("controllers", "--format", "json", include_model=False))
    controller = controllers["current-controller"]
    stdout = juju.cli(
        "clouds",
        "--controller",
        controller,
        "--format",
        "json",
        include_model=False,
    )

    clouds = json.loads(stdout)
    return set(value["type"] for value in clouds.values())


@contextmanager
def microk8s_kubernetes_cloud_and_model(
    juju: jubilant.Juju, microk8s_application: str
) -> Generator[tuple[jubilant.Juju, str], None, None]:
    """Create a temporary Kubernetes model backed by a MicroK8s application."""

    juju.cli("expose", microk8s_application)
    juju.config(microk8s_application, {"hostpath_storage": True})
    wait_for_apps(juju, [microk8s_application])

    unit = get_unit_name(juju, microk8s_application)
    rc, kubeconfig, _ = run_unit(juju, unit, "microk8s config -l")
    if rc != 0:
        raise Exception(f"failed to retrieve microk8s config {rc, kubeconfig}")

    public_address = juju.show_unit(unit).public_address
    kubeconfig = kubeconfig.replace("127.0.0.1", public_address)

    controllers = json.loads(juju.cli("controllers", "--format", "json", include_model=False))
    controller = controllers["current-controller"]
    model_suffix = uuid.uuid4().hex[:8]
    cloud_name = f"k8s-{model_suffix}"
    model_name = f"k8s-{model_suffix}"
    k8s_juju = jubilant.Juju()

    try:
        LOG.info("Add cloud %s on controller %s", cloud_name, controller)
        juju.cli(
            "add-k8s",
            cloud_name,
            "--client",
            "--controller",
            controller,
            include_model=False,
            stdin=kubeconfig,
        )

        k8s_juju.add_model(
            model_name, cloud=cloud_name, controller=controller, credential=cloud_name
        )
        yield k8s_juju, model_name
    finally:
        LOG.info("Destroy model %s", model_name)
        try:
            k8s_juju.destroy_model(k8s_juju.model or model_name, force=True, destroy_storage=True)
        except jubilant.CLIError:
            LOG.exception("failed to destroy model %s", model_name)

        LOG.info("Delete cloud %s on controller %s", cloud_name, controller)
        try:
            juju.cli(
                "remove-k8s",
                cloud_name,
                "--client",
                "--controller",
                controller,
                include_model=False,
            )
        except jubilant.CLIError:
            LOG.exception("failed to remove k8s cloud %s", cloud_name)
