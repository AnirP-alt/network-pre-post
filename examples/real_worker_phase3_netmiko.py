#!/usr/bin/env python3
"""Real worker example for Phase 3 using Netmiko (NX-OS).

This demonstrates plugging a real SSH-based per-host config application worker
into the Phase 3 orchestration. It uses Netmiko's ConnectHandler to push a
config snippet to NX-OS devices. If Netmiko is not available, this script will
gracefully report the missing dependency when executed.
"""

from typing import Dict, Any, Optional

def _real_worker(host: Dict[str, Any], config_text: Optional[str] = None) -> Dict[str, Any]:
    host_ip = host.get('host') or host.get('ip')
    username = host.get('username', 'admin')
    password = host.get('password', '')
    device_type = host.get('device_type', 'cisco_nxos')  # Netmiko device_type for NX-OS
    commands = [line for line in (config_text or '').splitlines() if line.strip()]
    output = ''
    try:
        from netmiko import ConnectHandler
        conn = ConnectHandler(
            device_type=device_type,
            host=host_ip,
            username=username,
            password=password,
            fast_cli=False,
        )
        if commands:
            output = conn.send_config_set(commands)
        # Quick verification command
        try:
            ver = conn.send_command("show version")
            output = (output or '') + "\n" + ver
        except Exception:
            pass
        conn.disconnect()
        return {'host': host_ip, 'status': 'success', 'output': output}
    except Exception as e:
        return {'host': host_ip, 'status': 'failed', 'error': str(e), 'output': None}

def _register():
    from nxos_config_diff_phase3 import set_phase3_worker
    from nxos_workers import real_netmiko_worker
    set_phase3_worker(real_netmiko_worker)

if __name__ == '__main__':
    _register()
    inventory = '[{"host": "rtr-demo", "ip": "10.0.0.99"}]'
    cfg = 'interface Gi0/1\n  no shutdown'
    from nxos_config_diff_phase3 import phase3_apply_inventory
    print(phase3_apply_inventory(inventory, cfg))
