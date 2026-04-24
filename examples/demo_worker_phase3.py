"""Minimal in-repo Phase 3 worker example.

This demonstrates how to provide a real per-host config application function
that Phase 3 orchestration can call. It defines a simple worker and a helper
to register it with the Phase 3 orchestration module.
"""

from nxos_config_diff_phase3 import set_phase3_worker, phase3_apply_inventory

def demo_worker(host: dict, config_text: str = None) -> dict:
    host_id = host.get('host') or host.get('ip')
    applied = len(config_text or '')
    return {
        'host': host_id,
        'status': 'success',
        'applied_chars': applied,
    }

def register_demo_worker():
    set_phase3_worker(demo_worker)

if __name__ == '__main__':
    register_demo_worker()
    inventory = '[{"host": "rtr-demo", "ip": "10.0.0.99"}]'
    cfg = 'interface Gi0/1\n  no shutdown'
    print(phase3_apply_inventory(inventory, cfg))
