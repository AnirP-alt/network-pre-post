from pathlib import Path
from typing import Optional

_LOGS_BASE_DIR: Optional[str] = None

def init_logging(base_dir: Optional[str] = None) -> str:
    global _LOGS_BASE_DIR
    _LOGS_BASE_DIR = base_dir
    logs_dir = Path(base_dir) if base_dir else Path('logs')
    logs_dir.mkdir(parents=True, exist_ok=True)
    return str(logs_dir)

def write_host_log(host: dict, text: str, base_dir: Optional[str] = None) -> str:
    host_id = str(host.get('host') or host.get('ip') or 'unknown')
    # Resolve base dir with explicit param or global default
    effective_base = base_dir or _LOGS_BASE_DIR
    logs_dir = Path(effective_base) if effective_base else Path('logs')
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / f"host_{host_id}.log"
    with open(path, 'a', encoding='utf-8') as f:
        f.write(str(text) + "\n")
    return str(path)

def write_fleet_log(text: str, base_dir: Optional[str] = None) -> str:
    effective_base = base_dir or _LOGS_BASE_DIR
    logs_dir = Path(effective_base) if effective_base else Path('logs')
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / "fleet.log"
    with open(path, 'a', encoding='utf-8') as f:
        f.write(str(text) + "\n")
    return str(path)
