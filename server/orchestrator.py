"""Orchestrator - Manages VMs, MicroVMs and their lifecycle.
Uses Firecracker for MicroVMs and QEMU/KVM for full VMs.
"""
import asyncio
import json
import logging
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger("setupo.orchestrator")

DATA_DIR = Path("/var/lib/setupo")
FC_DIR = DATA_DIR / "firecracker"
VM_DIR = DATA_DIR / "vms"
MICROVM_DIR = DATA_DIR / "microvms"


class VMType(str, Enum):
    VM = "vm"
    MICROVM = "microvm"


class VMState(str, Enum):
    CREATING = "creating"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class VMInstance:
    id: str
    name: str
    vm_type: VMType
    state: VMState = VMState.CREATING
    ip: str = ""
    vcpus: int = 1
    memory_mb: int = 256
    disk_mb: int = 512
    pid: Optional[int] = None
    capsules: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class Orchestrator:
    def __init__(self):
        self.instances: dict[str, VMInstance] = {}
        self._ip_counter_micro = 2  # 172.16.0.2+
        self._ip_counter_vm = 2     # 10.10.0.2+
        self._lock = asyncio.Lock()

    async def start(self):
        """Initialize orchestrator, recover any existing VMs."""
        logger.info("Orchestrator starting, scanning for existing instances...")
        for d in [VM_DIR, MICROVM_DIR, FC_DIR / "sockets"]:
            d.mkdir(parents=True, exist_ok=True)
        await self._recover_instances()

    async def stop(self):
        """Graceful shutdown of all managed instances."""
        logger.info("Stopping all instances...")
        for instance in list(self.instances.values()):
            if instance.state == VMState.RUNNING:
                await self.stop_instance(instance.id)

    async def _recover_instances(self):
        """Recover instance state from disk."""
        state_file = DATA_DIR / "state.json"
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text())
                for item in data.get("instances", []):
                    inst = VMInstance(**item)
                    inst.state = VMState.STOPPED
                    self.instances[inst.id] = inst
                logger.info("Recovered %d instances from state", len(self.instances))
            except Exception as e:
                logger.error("Failed to recover state: %s", e)

    async def _save_state(self):
        """Persist instance state to disk."""
        state_file = DATA_DIR / "state.json"
        data = {
            "instances": [inst.to_dict() for inst in self.instances.values()]
        }
        state_file.write_text(json.dumps(data, indent=2))

    # ── MicroVM (Firecracker) ────────────────────────────────────

    async def create_microvm(self, name: str, vcpus: int = 1, memory_mb: int = 256,
                              disk_mb: int = 512) -> VMInstance:
        """Create and boot a Firecracker MicroVM."""
        async with self._lock:
            instance_id = str(uuid.uuid4())[:8]
            ip = f"172.16.0.{self._ip_counter_micro}"
            self._ip_counter_micro += 1

        instance = VMInstance(
            id=instance_id,
            name=name,
            vm_type=VMType.MICROVM,
            ip=ip,
            vcpus=vcpus,
            memory_mb=memory_mb,
            disk_mb=disk_mb,
        )

        self.instances[instance_id] = instance
        logger.info("Creating MicroVM %s (%s) at %s", name, instance_id, ip)

        try:
            await self._boot_microvm(instance)
            instance.state = VMState.RUNNING
        except Exception as e:
            logger.error("Failed to create MicroVM %s: %s", instance_id, e)
            instance.state = VMState.ERROR
            instance.metadata["error"] = str(e)

        await self._save_state()
        return instance

    async def _boot_microvm(self, instance: VMInstance):
        """Boot a Firecracker MicroVM."""
        socket_path = FC_DIR / "sockets" / f"{instance.id}.sock"
        rootfs_src = FC_DIR / "rootfs" / "base.ext4"
        rootfs_dest = MICROVM_DIR / f"{instance.id}.ext4"

        # Copy rootfs for this instance
        if rootfs_src.exists():
            shutil.copy2(rootfs_src, rootfs_dest)
            if instance.disk_mb > 512:
                subprocess.run(
                    ["truncate", "-s", f"{instance.disk_mb}M", str(rootfs_dest)],
                    check=True,
                )
                subprocess.run(
                    ["e2fsck", "-f", "-y", str(rootfs_dest)],
                    capture_output=True,
                )
                subprocess.run(
                    ["resize2fs", str(rootfs_dest)],
                    capture_output=True,
                )

        # Create TAP interface for networking
        tap_name = f"tap-{instance.id[:6]}"
        subprocess.run(["ip", "tuntap", "add", tap_name, "mode", "tap"], check=True)
        subprocess.run(["ip", "link", "set", tap_name, "master", "br-micro"], check=True)
        subprocess.run(["ip", "link", "set", tap_name, "up"], check=True)

        # Firecracker config
        fc_config = {
            "boot-source": {
                "kernel_image_path": str(FC_DIR / "kernels" / "vmlinux"),
                "boot_args": (
                    f"console=ttyS0 reboot=k panic=1 pci=off "
                    f"ip={instance.ip}::172.16.0.1:255.255.255.0::eth0:off"
                ),
            },
            "drives": [
                {
                    "drive_id": "rootfs",
                    "path_on_host": str(rootfs_dest),
                    "is_root_device": True,
                    "is_read_only": False,
                }
            ],
            "machine-config": {
                "vcpu_count": instance.vcpus,
                "mem_size_mib": instance.memory_mb,
            },
            "network-interfaces": [
                {
                    "iface_id": "eth0",
                    "guest_mac": self._generate_mac(instance.id),
                    "host_dev_name": tap_name,
                }
            ],
        }

        config_path = MICROVM_DIR / f"{instance.id}.json"
        config_path.write_text(json.dumps(fc_config, indent=2))

        # Launch Firecracker
        proc = await asyncio.create_subprocess_exec(
            "firecracker",
            "--api-sock", str(socket_path),
            "--config-file", str(config_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        instance.pid = proc.pid
        instance.metadata["tap"] = tap_name
        logger.info("MicroVM %s booted (PID %d)", instance.id, proc.pid)

    # ── Full VM (QEMU/KVM) ───────────────────────────────────────

    async def create_vm(self, name: str, vcpus: int = 2, memory_mb: int = 1024,
                        disk_mb: int = 4096, image: str = "debian") -> VMInstance:
        """Create and boot a QEMU/KVM VM."""
        async with self._lock:
            instance_id = str(uuid.uuid4())[:8]
            ip = f"10.10.0.{self._ip_counter_vm}"
            self._ip_counter_vm += 1

        instance = VMInstance(
            id=instance_id,
            name=name,
            vm_type=VMType.VM,
            ip=ip,
            vcpus=vcpus,
            memory_mb=memory_mb,
            disk_mb=disk_mb,
            metadata={"image": image},
        )

        self.instances[instance_id] = instance
        logger.info("Creating VM %s (%s) at %s", name, instance_id, ip)

        try:
            await self._boot_vm(instance)
            instance.state = VMState.RUNNING
        except Exception as e:
            logger.error("Failed to create VM %s: %s", instance_id, e)
            instance.state = VMState.ERROR
            instance.metadata["error"] = str(e)

        await self._save_state()
        return instance

    async def _boot_vm(self, instance: VMInstance):
        """Boot a QEMU/KVM VM."""
        disk_path = VM_DIR / f"{instance.id}.qcow2"
        tap_name = f"vtap-{instance.id[:5]}"

        # Create disk
        subprocess.run([
            "qemu-img", "create", "-f", "qcow2",
            str(disk_path), f"{instance.disk_mb}M"
        ], check=True)

        # Create TAP interface
        subprocess.run(["ip", "tuntap", "add", tap_name, "mode", "tap"], check=True)
        subprocess.run(["ip", "link", "set", tap_name, "master", "br-vm"], check=True)
        subprocess.run(["ip", "link", "set", tap_name, "up"], check=True)

        # Launch QEMU
        proc = await asyncio.create_subprocess_exec(
            "qemu-system-x86_64",
            "-enable-kvm",
            "-m", str(instance.memory_mb),
            "-smp", str(instance.vcpus),
            "-drive", f"file={disk_path},format=qcow2",
            "-netdev", f"tap,id=net0,ifname={tap_name},script=no,downscript=no",
            "-device", "virtio-net-pci,netdev=net0",
            "-nographic",
            "-daemonize",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        instance.pid = proc.pid
        instance.metadata["tap"] = tap_name
        logger.info("VM %s booted (PID %d)", instance.id, proc.pid)

    # ── Common Operations ────────────────────────────────────────

    async def stop_instance(self, instance_id: str) -> VMInstance:
        """Stop a VM or MicroVM."""
        instance = self.instances.get(instance_id)
        if not instance:
            raise ValueError(f"Instance {instance_id} not found")

        if instance.pid:
            try:
                os.kill(instance.pid, 15)  # SIGTERM
                await asyncio.sleep(2)
                try:
                    os.kill(instance.pid, 0)
                    os.kill(instance.pid, 9)  # SIGKILL if still alive
                except ProcessLookupError:
                    pass
            except ProcessLookupError:
                pass

        # Cleanup TAP interface
        tap = instance.metadata.get("tap")
        if tap:
            subprocess.run(["ip", "link", "del", tap], capture_output=True)

        instance.state = VMState.STOPPED
        instance.pid = None
        await self._save_state()
        logger.info("Instance %s stopped", instance_id)
        return instance

    async def destroy_instance(self, instance_id: str) -> dict:
        """Destroy a VM/MicroVM and clean up all resources."""
        if instance_id not in self.instances:
            raise ValueError(f"Instance {instance_id} not found")

        instance = self.instances[instance_id]
        if instance.state == VMState.RUNNING:
            await self.stop_instance(instance_id)

        # Cleanup files
        if instance.vm_type == VMType.MICROVM:
            for ext in [".ext4", ".json"]:
                p = MICROVM_DIR / f"{instance_id}{ext}"
                p.unlink(missing_ok=True)
            sock = FC_DIR / "sockets" / f"{instance_id}.sock"
            sock.unlink(missing_ok=True)
        else:
            p = VM_DIR / f"{instance_id}.qcow2"
            p.unlink(missing_ok=True)

        del self.instances[instance_id]
        await self._save_state()
        logger.info("Instance %s destroyed", instance_id)
        return {"id": instance_id, "status": "destroyed"}

    async def exec_on_instance(self, instance_id: str, command: str) -> dict:
        """Execute a command on a VM/MicroVM via its slave agent."""
        instance = self.instances.get(instance_id)
        if not instance:
            raise ValueError(f"Instance {instance_id} not found")
        if instance.state != VMState.RUNNING:
            raise ValueError(f"Instance {instance_id} is not running")

        # Call the slave agent's API
        try:
            proc = await asyncio.create_subprocess_exec(
                "curl", "-s", "-m", "30",
                "-H", "Content-Type: application/json",
                "-d", json.dumps({"command": command}),
                f"http://{instance.ip}:9000/exec",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                return json.loads(stdout.decode())
            return {"error": stderr.decode(), "returncode": proc.returncode}
        except Exception as e:
            return {"error": str(e)}

    async def ssh_to_external(self, host: str, command: str, key_path: str = None) -> dict:
        """Execute a command on an external system via SSH (base can SSH out)."""
        ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10"]
        if key_path:
            ssh_cmd.extend(["-i", key_path])
        ssh_cmd.extend([host, command])

        try:
            proc = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return {
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
                "returncode": proc.returncode,
            }
        except Exception as e:
            return {"error": str(e)}

    def list_instances(self, vm_type: VMType = None) -> list[dict]:
        """List all instances, optionally filtered by type."""
        instances = self.instances.values()
        if vm_type:
            instances = [i for i in instances if i.vm_type == vm_type]
        return [i.to_dict() for i in instances]

    def get_instance(self, instance_id: str) -> dict:
        inst = self.instances.get(instance_id)
        if not inst:
            raise ValueError(f"Instance {instance_id} not found")
        return inst.to_dict()

    @staticmethod
    def _generate_mac(seed: str) -> str:
        """Generate a deterministic MAC address from a seed."""
        import hashlib
        h = hashlib.sha256(seed.encode()).hexdigest()
        return f"02:{h[0:2]}:{h[2:4]}:{h[4:6]}:{h[6:8]}:{h[8:10]}"
