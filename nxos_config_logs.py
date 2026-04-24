from pathlib import Path
from typing import Optional

def write_host_log(host: dict, text: str, base_dir: Optional[str] = None) -> str:
    host_id = str(host.get('host') or host.get('ip') or 'unknown')
    logs_dir = Path(base_dir) if base_dir else Path('logs')
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / f"host_{host_id}.log"
    with open(path, 'a', encoding='utf-8') as f:
        f.write(str(text) + "\n")
    return str(path)

def write_fleet_log(text: str, base_dir: Optional[str] = None) -> str:
    logs_dir = Path(base_dir) if base_dir else Path('logs')
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / "fleet.log"
    with open(path, 'a', encoding='utf-8') as f:
        f.write(str(text) + "\n")
    return str(path)
