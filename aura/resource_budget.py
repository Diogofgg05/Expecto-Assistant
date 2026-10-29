"""Expecto Performance 4.2: conservative, on-demand physical RAM guard.

Advisory host RAM measurements are not Ollama VRAM or LLM memory residency.
Never poll in background, inspect user content or change complex tasks.
"""
from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Callable
import ctypes
import os
import sys


@dataclass(frozen=True)
class HostMemory:
    total_mb: int
    available_mb: int

    def __post_init__(self) -> None:
        if not (0 < self.total_mb <= 1_048_576 and
                0 <= self.available_mb <= self.total_mb):
            raise ValueError("Invalid physical RAM readings")


def read_host_memory() -> HostMemory | None:
    """Read only physical RAM; never GPU/VRAM, swap or personal process data."""
    try:
        if sys.platform.startswith("linux"):
            # /proc/meminfo is a kernel facility; it might report host rather
            # than cgroup limits within containers. Treat as advisory only.
            with open("/proc/meminfo", "r", encoding="ascii") as stream:
                entries = stream.read(4096).splitlines()
            values = {}
            for line in entries:
                parts = line.split()
                if (len(parts) == 3 and parts[0] in {"MemTotal:", "MemAvailable:"}
                        and parts[2] == "kB"):
                    values[parts[0]] = int(parts[1]) // 1024
            return HostMemory(values["MemTotal:"], values["MemAvailable:"])
        if os.name == "nt":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            info = MEMORYSTATUSEX()
            info.dwLength = ctypes.sizeof(info)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(info)):
                return HostMemory(info.ullTotalPhys // (1024 * 1024),
                                  info.ullAvailPhys // (1024 * 1024))
    except (OSError, KeyError, ValueError, TypeError, AttributeError, OverflowError):
        return None
    return None


def pressure_bucket(sample: HostMemory | None) -> str:
    """Use a coarse signal; unknown never downscales anything."""
    if sample is None:
        return "unknown"
    ratio = sample.available_mb / sample.total_mb
    if sample.available_mb <= 512 or ratio <= 0.05:
        return "critical"
    if sample.available_mb <= 1024 or ratio <= 0.10:
        return "constrained"
    return "normal"


class AdaptiveMemoryBudget:
    """Short-lived OS sampling, with constant-sized counters and no worker."""

    def __init__(self, *, enabled: bool = True,
                 sampler: Callable[[], HostMemory | None] = read_host_memory,
                 clock: Callable[[], float] = monotonic,
                 ttl_seconds: float = 10.0):
        if not 1 <= ttl_seconds <= 300:
            raise ValueError("Invalid sampling interval")
        self.enabled, self.sampler, self.clock = enabled, sampler, clock
        self.ttl_seconds = ttl_seconds
        self._last_at: float | None = None
        self._bucket = "not_sampled"
        self._probes = 0
        self._downscaled = 0

    def bucket(self) -> str:
        if not self.enabled:
            return "disabled"
        now = self.clock()
        if self._last_at is not None and 0 <= now - self._last_at < self.ttl_seconds:
            return self._bucket
        self._last_at = now
        self._probes += 1
        try:
            self._bucket = pressure_bucket(self.sampler())
        except (OSError, ValueError, TypeError, RuntimeError):
            self._bucket = "unknown"
        return self._bucket

    def tune_quick(self, options: dict) -> dict:
        """Caller must only invoke for a short context-free Legacy question.

        Under high pressure cap already configured Ollama inference limits.
        Always return a new mapping; never increase allocations.
        """
        result = dict(options)
        state = self.bucket()
        if state == "constrained":
            ceilings = {"num_ctx": 2048, "num_batch": 32, "num_predict": 160}
        elif state == "critical":
            ceilings = {"num_ctx": 1536, "num_batch": 16, "num_predict": 112}
        else:
            return result
        changed = False
        for key, ceiling in ceilings.items():
            value = result.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value > ceiling:
                result[key] = ceiling
                changed = True
        if changed:
            self._downscaled += 1
        return result

    def status(self) -> dict:
        """Read-only and never triggers an OS sample or a new LLM connection."""
        return {
            "version": "4.2",
            "enabled": self.enabled,
            "last_pressure": self._bucket if self.enabled else "disabled",
            "probes": self._probes,
            "quick_requests_downscaled": self._downscaled,
            "sampling_ttl_seconds": self.ttl_seconds,
            "source": "host_physical_ram_not_ollama_vram",
            "background_monitor": False,
            "private_text_stored": False,
        }
