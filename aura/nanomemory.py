"""EXPECTO NanoMemory 7.0: bounded and reversible resource decisions.

This is a policy engine, not lossless model compression. RAM figures are
best-effort OS snapshots; VRAM must be queried from the model backend.
It never kills processes, evicts files, or modifies the Ollama installation.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import sys


GIB = 1024 ** 3


@dataclass(frozen=True)
class MemorySnapshot:
    total_bytes: int | None
    available_bytes: int | None
    source: str

    def public(self) -> dict:
        return {
            "total_mib": round(self.total_bytes / 1048576) if self.total_bytes is not None else None,
            "available_mib": round(self.available_bytes / 1048576) if self.available_bytes is not None else None,
            "source": self.source,
        }


@dataclass(frozen=True)
class MemoryPlan:
    requested: str
    effective: str
    low_memory: bool
    num_ctx: int
    keep_alive: str
    max_predict: int
    visual_fps: int
    visual_dpr: float
    visual_particles: int

    def public(self) -> dict:
        return {
            "requested": self.requested,
            "effective": self.effective,
            "low_memory": self.low_memory,
            "num_ctx": self.num_ctx,
            "keep_alive": self.keep_alive,
            "max_predict": self.max_predict,
            "visual_fps": self.visual_fps,
            "visual_dpr": self.visual_dpr,
            "visual_particles": self.visual_particles,
        }


def snapshot() -> MemorySnapshot:
    """Try optional psutil first, then lightweight platform facilities."""
    try:
        import psutil
        vm = psutil.virtual_memory()
        return MemorySnapshot(int(vm.total), int(vm.available), "psutil")
    except (ImportError, OSError, AttributeError):
        pass
    if sys.platform.startswith("linux"):
        try:
            values = {}
            for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
                name, _, raw = line.partition(":")
                if name in ("MemTotal", "MemAvailable"):
                    values[name] = int(raw.strip().split()[0]) * 1024
            if "MemTotal" in values and "MemAvailable" in values:
                return MemorySnapshot(values["MemTotal"], values["MemAvailable"], "proc_meminfo")
        except (OSError, ValueError, IndexError):
            pass
    elif sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            info = MEMORYSTATUSEX()
            info.dwLength = ctypes.sizeof(info)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(info)):
                return MemorySnapshot(int(info.ullTotalPhys), int(info.ullAvailPhys), "windows")
        except (OSError, AttributeError, ValueError):
            pass
    return MemorySnapshot(None, None, "unavailable")


def plan(
    mode: str,
    profile: str,
    memory: MemorySnapshot,
    configured_keep_alive: str = "10m",
    prediction: int = 450,
) -> MemoryPlan:
    if mode not in ("auto", "eco", "balanced", "max"):
        mode = "balanced"
    total, available = memory.total_bytes, memory.available_bytes
    pressure = bool(
        available is not None and total is not None and total > 0 and (
            available < 1.25 * GIB or available / total < 0.13
        )
    )
    if mode == "auto":
        if pressure or (total is not None and total <= 8 * GIB):
            effective = "eco"
        elif total is not None and available is not None and total >= 24 * GIB and available >= 8 * GIB:
            effective = "max"
        else:
            effective = "balanced"
    else:
        effective = mode
    # Emergency protection wins over explicit profiles, including MAX.
    if pressure:
        effective = "eco"
    contexts = {
        "eco": {"fast": 2048, "standard": 3072, "deep": 4096, "off": 4096},
        "balanced": {"fast": 4096, "standard": 8192, "deep": 12288, "off": 8192},
        "max": {"fast": 8192, "standard": 16384, "deep": 24576, "off": 16384},
    }
    keep_alive = "0m" if effective == "eco" else (
        "2m" if effective == "balanced" else configured_keep_alive
    )
    prediction_limit = {"eco": 700, "balanced": 1600, "max": 4096}[effective]
    fps, dpr, particles = {
        "eco": (12, 1.0, 45),
        "balanced": (24, 1.3, 100),
        "max": (40, 1.6, 145),
    }[effective]
    return MemoryPlan(
        requested=mode, effective=effective, low_memory=pressure,
        num_ctx=contexts[effective].get(profile, contexts[effective]["standard"]),
        keep_alive=keep_alive,
        max_predict=min(max(1, prediction), prediction_limit),
        visual_fps=fps, visual_dpr=dpr, visual_particles=particles,
    )


class NanoMemoryEngine:
    def __init__(self, settings):
        self.settings = settings
        self.last: MemoryPlan | None = None

    def decide(self, profile: str, prediction: int = 450) -> MemoryPlan:
        self.last = plan(
            getattr(self.settings, "nanomemory_mode", "auto"), profile,
            snapshot(), getattr(self.settings, "ollama_keep_alive", "10m"), prediction
        )
        return self.last

    def status(self) -> dict:
        reading = snapshot()
        decision = plan(
            getattr(self.settings, "nanomemory_mode", "auto"), "standard",
            reading, getattr(self.settings, "ollama_keep_alive", "10m")
        )
        return {"memory": reading.public(), "policy": decision.public(),
                "vram": "not_measured"}
