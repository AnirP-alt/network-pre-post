from typing import Any, Dict, Optional

def real_netmiko_worker(host: Dict[str, Any], config_text: Optional[str] = None) -> Dict[str, Any]:
    host_ip = host.get('host') or host.get('ip')
    device_type = host.get('device_type', 'cisco_nxos')
    username = host.get('username', 'admin')
    password = host.get('password', '')
    port = int(host.get('port', 22))
    timeout = int(host.get('timeout', 15))
    try:
        from netmiko import ConnectHandler
        conn = ConnectHandler(
            device_type=device_type,
            host=host_ip,
            username=username,
            password=password,
            port=port,
            timeout=timeout,
        )
        cmds = [line for line in (config_text or '').splitlines() if line.strip()]
        output = ''
        if cmds:
            output = conn.send_config_set(cmds)
        try:
            ver = conn.send_command("show version")
        except Exception:
            ver = ''
        conn.disconnect()
        combined = ((output or '') + ('\n' + ver if ver else ''))
        return {'host': host_ip, 'status': 'success', 'output': combined}
    except Exception as e:
        return {'host': host_ip, 'status': 'failed', 'error': str(e), 'output': None}
