#!/bin/bash
# Install Firecracker MicroVM hypervisor
set -euo pipefail

ARCH=$(uname -m)
FC_VERSION="1.6.0"

echo "[setupo] Installing Firecracker ${FC_VERSION} for ${ARCH}..."

# Download Firecracker binary
curl -fsSL -o /tmp/firecracker.tgz \
  "https://github.com/firecracker-microvm/firecracker/releases/download/v${FC_VERSION}/firecracker-v${FC_VERSION}-${ARCH}.tgz"

tar -xzf /tmp/firecracker.tgz -C /tmp
mv /tmp/release-v${FC_VERSION}-${ARCH}/firecracker-v${FC_VERSION}-${ARCH} /usr/local/bin/firecracker
mv /tmp/release-v${FC_VERSION}-${ARCH}/jailer-v${FC_VERSION}-${ARCH} /usr/local/bin/jailer
chmod +x /usr/local/bin/firecracker /usr/local/bin/jailer

# Create directory for microVM rootfs and kernels
mkdir -p /var/lib/setupo/firecracker/kernels
mkdir -p /var/lib/setupo/firecracker/rootfs
mkdir -p /var/lib/setupo/firecracker/sockets

# Download a minimal kernel for microVMs
curl -fsSL -o /var/lib/setupo/firecracker/kernels/vmlinux \
  "https://s3.amazonaws.com/spec.ccfc.min/img/quickstart_guide/${ARCH}/kernels/vmlinux.bin" || \
  echo "[setupo] WARNING: Could not download kernel, will need manual setup"

# Create a minimal rootfs base image
echo "[setupo] Creating base rootfs for microVMs..."
truncate -s 512M /var/lib/setupo/firecracker/rootfs/base.ext4
mkfs.ext4 -F /var/lib/setupo/firecracker/rootfs/base.ext4

# Mount and populate base rootfs with slave agent
MOUNT_DIR=$(mktemp -d)
mount /var/lib/setupo/firecracker/rootfs/base.ext4 "$MOUNT_DIR"

# Install minimal system into rootfs
if command -v debootstrap &>/dev/null; then
  debootstrap --include=python3,python3-pip,curl,iproute2 \
    bookworm "$MOUNT_DIR" http://deb.debian.org/debian || true
fi

# Copy slave agent into rootfs
mkdir -p "$MOUNT_DIR/opt/setupo-slave"
if [ -d /opt/setupo/slave ]; then
  cp -r /opt/setupo/slave/* "$MOUNT_DIR/opt/setupo-slave/"
fi

umount "$MOUNT_DIR"
rmdir "$MOUNT_DIR"

rm -rf /tmp/firecracker.tgz /tmp/release-v${FC_VERSION}-${ARCH}

echo "[setupo] Firecracker installed successfully"
