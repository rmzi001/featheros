# Reproducible container environment for building FeatherOS Live ISO
# Usage:
#   docker build -t featheros-builder -f build/Dockerfile .
#   docker run --rm --privileged -v "$(pwd):/workspace" featheros-builder
FROM debian:trixie

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    debootstrap \
    dosfstools \
    grub-common \
    grub-efi-amd64-bin \
    grub-pc-bin \
    mtools \
    python3 \
    squashfs-tools \
    xorriso \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
ENTRYPOINT ["/bin/bash", "/workspace/build/build-iso.sh"]
