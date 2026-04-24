import json
import sys
from typing import Any, Dict, List, Callable
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

_ph3_worker: Callable[[Dict[str, Any]], Dict[str, Any]] | None = None

def set_phase3_worker(worker_func: Callable[[Dict[str, Any]], Dict[str, Any]]):
    """Public helper to inject a custom per-host worker function for Phase 3."""
    global _ph3_worker
    _ph3_worker = worker_func  # type: ignore

def phase3_apply_inventory(inventory_json: str, config_text: str) -> List[Dict[str, Any]]:
    """
    Public entry for Phase 3 multi-device config application.
    Returns per-host results.
    """
    hosts = parse_host_inventory(inventory_json)
    # Use an injected worker if provided; else use the default that applies config_to_host
    if _ph3_worker is not None:
        # Support workers that accept (host, config_text) or only (host)
        def worker(h):
            try:
                return _ph3_worker(h, config_text)  # type: ignore
            except TypeError:
                return _ph3_worker(h)  # type: ignore
        
        # If the injected worker is a callable with a different signature, the above
        # wrapper will adapt to either form.
    else:
        def worker(h):
            return apply_config_to_host(h, config_text)
    return _run_on_hosts_parallel(hosts, worker)
