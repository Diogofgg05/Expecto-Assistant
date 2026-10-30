"""Fingerprint benchmark workload, local CPU/RAM and exact Ollama model digest.

No hostname, user identifier, serial number, prompts or model outputs are stored.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re

import httpx

BENCHMARK_PROMPT = 'Responde em JSON: {"answer":"OK"}.'
SCHEMA_VERSION = 2


def hardware_profile() -> dict:
    system = platform.system()
    processor = platform.processor().strip()
    if not processor and system == "Linux":
        try:
            with open("/proc/cpuinfo", encoding="utf-8") as stream:
                processor = next(
                    (line.split(":", 1)[1].strip() for line in stream
                     if line.startswith("model name") and ":" in line), "")
        except (OSError, StopIteration):
            pass
    ram_bytes = None
    if system == "Windows":
        try:
            import ctypes
            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong),
                    ("available_physical", ctypes.c_ulonglong),
                    ("total_page", ctypes.c_ulonglong),
                    ("available_page", ctypes.c_ulonglong),
                    ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended", ctypes.c_ulonglong)]
            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                ram_bytes = int(status.total_physical)
        except (AttributeError, OSError, ValueError):
            pass
    elif hasattr(os, "sysconf"):
        try:
            ram_bytes = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        except (OSError, ValueError):
            pass
    return {
        "system": system,
        "architecture": platform.machine(),
        "cpu_model": processor or None,
        "logical_cpus": os.cpu_count(),
        "physical_ram_bytes": ram_bytes,
    }


async def fetch_model_digest(url: str, model: str) -> str:
    """Resolve an installed tag; fail instead of comparing unknown model weights."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=3.0),
                                 follow_redirects=False, trust_env=False) as client:
        response = await client.get(url.rstrip("/") + "/api/tags")
        response.raise_for_status()
        models = response.json().get("models", [])
    if not isinstance(models, list):
        raise ValueError("Invalid Ollama tags response")
    wanted = model if ":" in model else model + ":latest"
    for entry in models:
        if not isinstance(entry, dict):
            continue
        if entry.get("name") != wanted and entry.get("model") != wanted:
            continue
        digest = entry.get("digest")
        if isinstance(digest, str) and re.fullmatch(r"(?:sha256:)?[a-fA-F0-9]{64}", digest):
            return digest.lower().removeprefix("sha256:")
        raise ValueError("Installed Ollama model has no verifiable digest")
    raise ValueError("Model tag not found in local Ollama; use the exact installed model name")


async def collect_identity(url: str, model: str) -> dict:
    host = hardware_profile()
    if (not host["cpu_model"] or not host["logical_cpus"]
            or not isinstance(host["physical_ram_bytes"], int)
            or host["physical_ram_bytes"] <= 0):
        raise RuntimeError("Unable to identify CPU/RAM reliably for a comparable benchmark")
    return {
        "schema_version": SCHEMA_VERSION,
        "model_digest": await fetch_model_digest(url, model),
        "workload_sha256": hashlib.sha256(BENCHMARK_PROMPT.encode("utf-8")).hexdigest(),
        "hardware": host,
    }
