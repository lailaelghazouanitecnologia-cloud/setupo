#!/bin/bash
# Setup networking for VMs and MicroVMs
set -euo pipefail

echo "[setupo] Configuring network bridges..."

# Enable IP forwarding
echo 1 > /proc/sys/net/ipv4/ip_forward
echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf

# Bridge for MicroVMs (172.16.0.0/24)
ip link add name br-micro type bridge 2>/dev/null || true
ip addr add 172.16.0.1/24 dev br-micro 2>/dev/null || true
ip link set br-micro up

# Bridge for full VMs (10.10.0.0/24)
ip link add name br-vm type bridge 2>/dev/null || true
ip addr add 10.10.0.1/24 dev br-vm 2>/dev/null || true
ip link set br-vm up

# NAT for outbound traffic from VMs/MicroVMs
MAIN_IF=$(ip route | grep default | awk '{print $5}' | head -1)

iptables -t nat -A POSTROUTING -s 172.16.0.0/24 -o "$MAIN_IF" -j MASQUERADE
iptables -t nat -A POSTROUTING -s 10.10.0.0/24 -o "$MAIN_IF" -j MASQUERADE

# Allow forwarding between bridges and main interface
iptables -A FORWARD -i br-micro -o "$MAIN_IF" -j ACCEPT
iptables -A FORWARD -i "$MAIN_IF" -o br-micro -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i br-vm -o "$MAIN_IF" -j ACCEPT
iptables -A FORWARD -i "$MAIN_IF" -o br-vm -m state --state RELATED,ESTABLISHED -j ACCEPT

# Allow inter-bridge communication (VMs can talk to MicroVMs)
iptables -A FORWARD -i br-micro -o br-vm -j ACCEPT
iptables -A FORWARD -i br-vm -o br-micro -j ACCEPT

# Save iptables rules
mkdir -p /etc/iptables
iptables-save > /etc/iptables/rules.v4

# Persist bridge config
cat > /etc/network/interfaces.d/setupo-bridges <<'EOF'
auto br-micro
iface br-micro inet static
    address 172.16.0.1
    netmask 255.255.255.0
    bridge_ports none
    bridge_stp off

auto br-vm
iface br-vm inet static
    address 10.10.0.1
    netmask 255.255.255.0
    bridge_ports none
    bridge_stp off
EOF

echo "[setupo] Network bridges configured:"
echo "  br-micro: 172.16.0.0/24 (Firecracker MicroVMs)"
echo "  br-vm:    10.10.0.0/24  (QEMU/KVM VMs)"
