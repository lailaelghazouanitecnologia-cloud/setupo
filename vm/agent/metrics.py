"""
Real-time system metrics endpoint for the NSO agent.
Provides CPU, memory, disk, network, and process-level stats.
"""

import os
import time
import logging
from pathlib import Path

from fastapi import APIRouter, Depends
from auth import AdminUser, require_admin

logger = logging.getLogger("nso-agent.metrics")
router = APIRouter(prefix="/metrics", tags=["metrics"])

# Cache CPU readings for delta calculation
_prev_cpu: dict | None = None
_prev_cpu_time: float = 0.0


def _read_cpu() -> dict:
    """Read /proc/stat for CPU usage calculation."""
    global _prev_cpu, _prev_cpu_time
    try:
        with open("/proc/stat") as f:
            line = f.readline()
        parts = line.split()
        # user, nice, system, idle, iowait, irq, softirq, steal
        fields = ["user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal"]
        current = {fields[i]: int(parts[i + 1]) for i in range(min(len(fields), len(parts) - 1))}

        now = time.monotonic()
        result = {"cores": os.cpu_count() or 1}

        if _prev_cpu and (now - _prev_cpu_time) > 0.05:
            total_delta = sum(current[k] - _prev_cpu.get(k, 0) for k in fields if k in current)
            idle_delta = (current.get("idle", 0) - _prev_cpu.get("idle", 0)) + \
                         (current.get("iowait", 0) - _prev_cpu.get("iowait", 0))
            if total_delta > 0:
                result["percent"] = round((1 - idle_delta / total_delta) * 100, 1)
                result["user"] = round((current["user"] - _prev_cpu.get("user", 0)) / total_delta * 100, 1)
                result["system"] = round((current["system"] - _prev_cpu.get("system", 0)) / total_delta * 100, 1)
                result["iowait"] = round((current.get("iowait", 0) - _prev_cpu.get("iowait", 0)) / total_delta * 100, 1)
            else:
                result["percent"] = 0.0
        else:
            # First call — use load average as estimate
            try:
                la = os.getloadavg()
                cores = result["cores"]
                result["percent"] = round(min(la[0] / cores * 100, 100), 1)
            except OSError:
                result["percent"] = 0.0

        _prev_cpu = current
        _prev_cpu_time = now
        return result
    except Exception:
        return {"percent": 0.0, "cores": os.cpu_count() or 1}


def _read_memory() -> dict:
    """Read /proc/meminfo for memory stats."""
    try:
        mem = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    mem[parts[0].rstrip(":")] = int(parts[1])
                if len(mem) > 10:
                    break

        total = mem.get("MemTotal", 1)
        available = mem.get("MemAvailable", mem.get("MemFree", 0))
        used = total - available
        swap_total = mem.get("SwapTotal", 0)
        swap_free = mem.get("SwapFree", 0)

        return {
            "total_mb": round(total / 1024),
            "used_mb": round(used / 1024),
            "available_mb": round(available / 1024),
            "percent": round(used / total * 100, 1) if total else 0,
            "swap_total_mb": round(swap_total / 1024),
            "swap_used_mb": round((swap_total - swap_free) / 1024),
        }
    except Exception:
        return {"total_mb": 0, "used_mb": 0, "available_mb": 0, "percent": 0}


def _read_disk() -> dict:
    """Disk usage for root filesystem."""
    try:
        st = os.statvfs("/")
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = total - free
        return {
            "total_gb": round(total / (1024**3), 1),
            "used_gb": round(used / (1024**3), 1),
            "free_gb": round(free / (1024**3), 1),
            "percent": round(used / total * 100, 1) if total else 0,
        }
    except Exception:
        return {"total_gb": 0, "used_gb": 0, "free_gb": 0, "percent": 0}


def _read_network() -> dict:
    """Read /proc/net/dev for network I/O."""
    try:
        result = {}
        with open("/proc/net/dev") as f:
            for line in f:
                if ":" not in line:
                    continue
                iface, data = line.split(":", 1)
                iface = iface.strip()
                if iface == "lo":
                    continue
                parts = data.split()
                if len(parts) >= 9:
                    result[iface] = {
                        "rx_bytes": int(parts[0]),
                        "rx_mb": round(int(parts[0]) / (1024**2), 1),
                        "tx_bytes": int(parts[8]),
                        "tx_mb": round(int(parts[8]) / (1024**2), 1),
                    }
        return result
    except Exception:
        return {}


def _read_processes() -> list[dict]:
    """Read key processes from /proc for process-level metrics."""
    procs = []
    nso_keywords = {"uvicorn", "nginx", "node", "python", "nso", "certbot"}

    try:
        for pid_dir in Path("/proc").iterdir():
            if not pid_dir.name.isdigit():
                continue
            try:
                cmdline = (pid_dir / "cmdline").read_text().replace("\x00", " ").strip()
                if not cmdline:
                    continue

                # Only include NSO-relevant processes
                cmd_lower = cmdline.lower()
                if not any(kw in cmd_lower for kw in nso_keywords):
                    continue

                # Read process stats
                stat_line = (pid_dir / "stat").read_text().split()
                name = stat_line[1].strip("()")
                state = stat_line[2]

                # Memory from /proc/PID/status
                rss_kb = 0
                try:
                    for line in (pid_dir / "status").read_text().splitlines():
                        if line.startswith("VmRSS:"):
                            rss_kb = int(line.split()[1])
                            break
                except Exception:
                    pass

                procs.append({
                    "pid": int(pid_dir.name),
                    "name": name,
                    "state": state,
                    "rss_mb": round(rss_kb / 1024, 1),
                    "cmd": cmdline[:200],
                })
            except (PermissionError, FileNotFoundError, ProcessLookupError):
                continue
    except Exception:
        pass

    return sorted(procs, key=lambda p: p["rss_mb"], reverse=True)[:20]


def _read_load() -> dict:
    """Load average and uptime."""
    result = {}
    try:
        la = os.getloadavg()
        result["load_1m"] = round(la[0], 2)
        result["load_5m"] = round(la[1], 2)
        result["load_15m"] = round(la[2], 2)
    except OSError:
        pass

    try:
        with open("/proc/uptime") as f:
            result["uptime_seconds"] = int(float(f.read().split()[0]))
    except Exception:
        pass

    return result


@router.get("")
async def get_metrics(admin: AdminUser = Depends(require_admin)):
    """Full system metrics snapshot."""
    return {
        "timestamp": int(time.time()),
        "cpu": _read_cpu(),
        "memory": _read_memory(),
        "disk": _read_disk(),
        "network": _read_network(),
        "load": _read_load(),
        "processes": _read_processes(),
    }


@router.get("/summary")
async def get_metrics_summary(admin: AdminUser = Depends(require_admin)):
    """Compact metrics for dashboard polling (CPU%, mem%, disk%)."""
    cpu = _read_cpu()
    mem = _read_memory()
    disk = _read_disk()
    load = _read_load()

    return {
        "cpu_percent": cpu.get("percent", 0),
        "mem_percent": mem.get("percent", 0),
        "mem_used_mb": mem.get("used_mb", 0),
        "mem_total_mb": mem.get("total_mb", 0),
        "disk_percent": disk.get("percent", 0),
        "disk_used_gb": disk.get("used_gb", 0),
        "disk_total_gb": disk.get("total_gb", 0),
        "load_1m": load.get("load_1m", 0),
        "uptime": load.get("uptime_seconds", 0),
    }
