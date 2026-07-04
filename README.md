# Anti-deprecation notice

This charm is a fork of the original charm-microk8s repo and publishes under the charm name ```microk8s-ng```. The objective of this fork is add supported versions of microk8s to it to act as a medium-term bridge for people/orgs who have not migrated to the newer ```k8s``` charm.

# MicroK8s

## The smallest, fastest Kubernetes

Single-package fully conformant lightweight Kubernetes that works on [42 flavours of Linux](https://snapcraft.io/microk8s). Perfect for:

- Developer workstations
- IoT
- Edge
- CI/CD

## Usage

This charm deploys and manages a MicroK8s cluster. It can handle scaling up and down.

**Minimum Requirements**: 1 vCPU and 2GB RAM.

**Recommended Requirements**: 2 vCPUs and 4GB RAM, 20GB disk.

Make sure to account for extra requirements depending on the workload you are planning to deploy.

```bash
juju deploy microk8s --constraints 'cores=2 mem=4G'
```

Alternatively, to specify the MicroK8s version to install, you can use:

```bash
juju deploy microk8s --constraints 'cores=2 mem=4G' --config channel=1.35/stable
```
