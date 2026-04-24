"""Demo: Hooking in a real per-host apply function for Phase 3.

This is a small, self-contained example showing how you would plug in a real
device interaction (SSH via Netmiko/NAPALM, etc.) by defining a global hook
named apply_config_for_host that phase3_apply_inventory will call for each host.
"""

from nxos_config_diff_phase3 import phase3_apply_inventory

def apply_config_for_host(host: dict, config_text: str) -> dict:
    # Real implementation would connect to the host and push the config
    # For demonstration, we simulate a successful apply and return a summary
    return {
        'host': host.get('host') or host.get('ip'),
        'status': 'success',
        'applied_chars': len(config_text) if config_text else 0,
    }

# Expose the hook so phase3_apply_inventory can use it
globals()['apply_config_for_host'] = apply_config_for_host

if __name__ == '__main__':
  inventory = '[{"host":"rtr-demo","ip":"10.0.0.99"}]'
  cfg = 'interface Gi0/1\n  no shutdown'
  print(phase3_apply_inventory(inventory, cfg))
