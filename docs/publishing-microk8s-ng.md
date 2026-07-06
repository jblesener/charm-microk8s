# Publishing microk8s-ng

The `Publish microk8s-ng charm` GitHub Actions workflow builds this charm with
the Charmhub package name `microk8s-ng` and publishes it to `latest/edge`.

The committed `metadata.yaml` uses the `microk8s-ng` package name. The workflow
verifies that name before packing the charm.

## Charmhub setup

Install Charmcraft and log in with the account that should own or publish the
Charmhub package:

```bash
sudo snap install charmcraft --classic
charmcraft login
```

Register the package if it does not already exist:

```bash
charmcraft register microk8s-ng
```

If the package already exists, confirm the publishing account is a collaborator
with upload permission for `microk8s-ng`.

Confirm that the `latest` track exists for the package. If it does not, create
or request the track before running the workflow.

## GitHub Actions auth

Export a Charmhub credential for CI:

```bash
charmcraft login --export=charmcraft-auth.txt --channel=latest/edge --permission=package-manage --permission=package-view --charm=microk8s-ng --ttl 31536000
```

Create a repository Actions secret:

- Secret name: `CHARMCRAFT_AUTH`
- Secret value: the full contents of `charmcraft-auth.txt`
- Location: GitHub repository `Settings` -> `Secrets and variables` -> `Actions`

Remove the local exported credential after creating the secret:

```bash
rm charmcraft-auth.txt
```

## Publishing

The workflow publishes automatically on pushes to `master`. It can also be run
manually from the GitHub Actions tab with `workflow_dispatch`.

Manual runs include an optional `debug_enabled` input that opens a tmate session
if the workflow reaches the debug step.

### Releasing to beta/stable

```
   charmcraft release microk8s-ng --revision=9 --channel=latest/beta
   charmcraft release microk8s-ng --revision=9 --channel=latest/stable
```
