#
# Copyright 2023 Canonical, Ltd.
#

# Snap store channel to use when installing MicroK8s by default.
SNAP_CHANNEL = "latest/edge"

MICROK8S_STABLE_CHANNELS = tuple(f"1.{minor}/stable" for minor in range(28, 37))
SUPPORTED_MICROK8S_CHANNELS = (SNAP_CHANNEL, *MICROK8S_STABLE_CHANNELS)


def normalize_channel(channel: str) -> str:
    if not channel:
        return SNAP_CHANNEL

    if "/" not in channel and channel.startswith("1."):
        return f"{channel}/stable"

    return channel


def validate_channel(channel: str) -> str:
    normalized_channel = normalize_channel(channel)
    if normalized_channel not in SUPPORTED_MICROK8S_CHANNELS:
        raise ValueError("channel must be one of {}".format(", ".join(SUPPORTED_MICROK8S_CHANNELS)))

    return normalized_channel
