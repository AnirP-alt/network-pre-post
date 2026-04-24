import json
from typing import Any, Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

def parse_host_inventory(inv_content: str) -> List[Dict[str, Any]]:
    """
    Parse host inventory JSON into a list of host dicts.
    Supports a JSON array of objects with keys like host, ip, username, password.
    """
    try:
        data = json.loads(inv_content)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []

def _run_on_hosts_parallel(hosts: List[Dict[str, Any]], worker):
    results: List[Dict[str, Any]] = []
    if not hosts:
        return results
    max_workers = min(16, max(1, len(hosts)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(worker, h): h for h in hosts}
        for fut in as_completed(futures):
            host = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:
                res = {'host': host.get('host') or host.get('ip'), 'status': 'error', 'error': str(exc)}
            results.append(res)
    return results

def apply_config_to_host(host: Dict[str, Any], config_text: str) -> Dict[str, Any]:
    """
    Placeholder single-host config application hook.
    If a concrete implementation exists elsewhere, this will be replaced by that.
    """
    if 'apply_config_for_host' in globals():
        return apply_config_for_host(host, config_text)
    return {'host': host.get('host') or host.get('ip'), 'status': 'skipped', 'detail': 'no single-host apply available'}

def phase3_apply_inventory(inventory_json: str, config_text: str) -> List[Dict[str, Any]]:
    """
    Public entry for Phase 3 multi-device config application.
    Returns per-host results.
    """
    hosts = parse_host_inventory(inventory_json)
    def worker(h):
        return apply_config_to_host(h, config_text)
    return _run_on_hosts_parallel(hosts, worker)
