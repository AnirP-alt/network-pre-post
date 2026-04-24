"""Phase 4 tests: fleet and per-host logging"""

import json
from pathlib import Path

import nxos_config_diff as app


def test_fleet_log_creation(tmp_path):
    results = [
        {"host": "host1", "success": True, "added_count": 2, "removed_count": 1, "error": None},
        {"host": "host2", "success": False, "added_count": 0, "removed_count": 0, "error": "Timeout"},
    ]
    path = app.write_fleet_log(results, tmp_path)
    assert path is not None
    assert Path(path).exists()
    content = json.loads(Path(path).read_text())
    assert "hosts" in content and len(content["hosts"]) == 2


def test_host_log_write(tmp_path):
    log = app.write_host_log("host1", tmp_path, {"hello": "world"})
    assert log is not None and Path(log).exists()
