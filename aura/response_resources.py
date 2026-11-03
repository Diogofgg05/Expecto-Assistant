"""Sampled response resources; missing measurements are null, never zero guesses."""
from __future__ import annotations
import asyncio
from contextlib import suppress
import os
import math
import time


def ram_sample():
    try:
        import psutil
        own = psutil.Process(os.getpid()).memory_info().rss
        ollama = []
        for process in psutil.process_iter(['name', 'memory_info']):
            try:
                if 'ollama' in (process.info['name'] or '').lower():
                    ollama.append(process.info['memory_info'].rss)
            except (psutil.Error, AttributeError):
                pass
        return {'app_rss_bytes': own, 'ollama_rss_bytes': sum(ollama) if ollama else None}
    except (ImportError, OSError):
        return {'app_rss_bytes': None, 'ollama_rss_bytes': None}


class ResponseResources:
    """RSS is process accounting, not incremental allocation; /ps is model VRAM.

    Ollama RSS covers visible local Ollama processes (shared pages may be counted
    twice), not remote/container servers. Sampling may miss short-lived peaks.
    """
    def __init__(self, vram_probe=None, interval=0.5):
        self.probe = vram_probe
        self.interval = max(0.1, interval)
        self.peaks = dict.fromkeys(('app_rss_bytes', 'ollama_rss_bytes', 'loaded_vram_bytes'))
        self.counts = dict.fromkeys(self.peaks, 0)
        self.samples = 0
        self.errors = 0
        self.overhead_ms = 0.0
        self.task = None

    async def sample(self):
        began = time.perf_counter()
        try:
            values = await asyncio.to_thread(ram_sample)
        except Exception:
            # Optional telemetry must never replace a successful answer with an error.
            values = {}
            self.errors += 1
        if not isinstance(values, dict):
            values = {}
            self.errors += 1
        if self.probe:
            try:
                result = await asyncio.wait_for(self.probe(), timeout=1)
                v = result.get('loaded_vram_mib')
                if result.get('available') and type(v) in (int, float) and math.isfinite(v) and v >= 0:
                    values['loaded_vram_bytes'] = round(v * 1048576)
            except Exception:
                self.errors += 1
        for key, value in values.items():
            if key in self.peaks and type(value) in (int, float) and math.isfinite(value) and value >= 0:
                self.peaks[key] = max(self.peaks[key] or 0, value)
                self.counts[key] += 1
        self.samples += 1
        self.overhead_ms += (time.perf_counter() - began) * 1000

    async def loop(self):
        while True:
            await self.sample()
            await asyncio.sleep(self.interval)

    async def __aenter__(self):
        self.task = asyncio.create_task(self.loop())
        return self

    async def __aexit__(self, *args):
        self.task.cancel()
        with suppress(asyncio.CancelledError):
            await self.task

    def public(self):
        return {'sampled_peak_bytes': dict(self.peaks), 'valid_samples': dict(self.counts),
                'sample_count': self.samples, 'probe_errors': self.errors, 'sample_interval_ms': self.interval * 1000,
                'probe_wall_ms': round(self.overhead_ms, 2),
                'scope': 'application RSS; visible local Ollama RSS; all loaded Ollama model VRAM',
                'exact_peak': False}
