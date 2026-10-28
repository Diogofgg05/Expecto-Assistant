"""Non-secret configuration. .env loaded by launch scripts or external process."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path | None = None) -> None:
    path = path or ROOT / '.env'
    if not path.exists():
        return
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        if key.startswith('AURA_'):
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    host: str = '127.0.0.1'
    port: int = 8000
    data_dir: Path = ROOT / 'data'
    ollama_url: str = 'http://127.0.0.1:11434'
    ollama_model: str = 'hermes3'
    embedding_model: str = ''
    compute_profile: str = 'balanced'
    compute_fast_model: str = ''
    compute_memory_budget_mb: int = 0
    compute_gpu_mode: str = 'auto'
    compute_max_active: int = 2
    compute_max_waiting: int = 4
    searxng_url: str = ''
    research_interval_hours: int = 24
    voice_output: bool = True
    episodic_lookback_months: int = 6
    episodic_capture: bool = True
    memory_backup_days: int = 7
    auto_extract_memory: bool = True
    auto_link_memory: bool = True
    auto_consolidate_memory: bool = False  # Opt-in; no unrequested topic indexing.
    memory_worker_interval_seconds: int = 45
    database_passphrase: str = field(default="", repr=False)
    database_encryption_required: bool = True  # Tests/explicit legacy migration only disable.
    backup_passphrase: str = field(default="", repr=False)  # Never log secrets

    @classmethod
    def from_env(cls) -> 'Settings':
        load_dotenv()
        directory = Path(os.getenv('AURA_DATA_DIR', './data')).expanduser()
        if not directory.is_absolute():
            directory = ROOT / directory
        return cls(
            host=os.getenv('AURA_HOST', '127.0.0.1'),
            port=int(os.getenv('AURA_PORT', '8000')),
            data_dir=directory,
            ollama_url=os.getenv('AURA_OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/'),
            ollama_model=os.getenv('AURA_OLLAMA_MODEL', 'hermes3'),
            embedding_model=os.getenv('AURA_EMBEDDING_MODEL', ''),
            compute_profile=os.getenv('AURA_COMPUTE_PROFILE', 'balanced'),
            compute_fast_model=os.getenv('AURA_COMPUTE_FAST_MODEL', ''),
            compute_memory_budget_mb=int(os.getenv('AURA_COMPUTE_MEMORY_BUDGET_MB', '0')),
            compute_gpu_mode=os.getenv('AURA_COMPUTE_GPU_MODE', 'auto'),
            compute_max_active=int(os.getenv('AURA_COMPUTE_MAX_ACTIVE', '2')),
            compute_max_waiting=int(os.getenv('AURA_COMPUTE_MAX_WAITING', '4')),
            searxng_url=os.getenv('AURA_SEARXNG_URL', '').rstrip('/'),
            research_interval_hours=max(6, min(168, int(os.getenv('AURA_RESEARCH_INTERVAL_HOURS', '24')))),
            voice_output=os.getenv('AURA_VOICE_OUTPUT', 'true').lower() not in ('false', '0', 'no'),
            episodic_lookback_months=max(1, min(60, int(os.getenv('AURA_MEMORY_MONTHS', '6')))),
            episodic_capture=os.getenv('AURA_EPISODIC_CAPTURE', 'true').lower() not in ('false','0','no'),
            memory_backup_days=max(1, min(90, int(os.getenv('AURA_MEMORY_BACKUP_DAYS', '7')))),
            auto_extract_memory=os.getenv('AURA_AUTO_EXTRACT_MEMORY', 'true').lower() not in ('false','0','no'),
            auto_link_memory=os.getenv('AURA_AUTO_LINK_MEMORY', 'true').lower() not in ('false','0','no'),
            auto_consolidate_memory=os.getenv('AURA_AUTO_CONSOLIDATE_MEMORY', 'false').lower() not in ('false','0','no'),
            memory_worker_interval_seconds=max(10, min(600,int(os.getenv('AURA_MEMORY_WORKER_SECONDS','45')))),
            database_passphrase=os.getenv('AURA_DATABASE_PASSPHRASE', ''),
            backup_passphrase=os.getenv('AURA_BACKUP_PASSPHRASE', ''),
        )
