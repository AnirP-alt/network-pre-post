import builtins
import types
import pytest

def test_real_worker_path_monkeypatched(monkeypatch):
    # Create a fake ConnectHandler to mock Netmiko behavior
    class FakeConn:
        def __init__(self, *args, **kwargs):
            pass
        def send_config_set(self, cmds):
            return "configured:" + ";".join(cmds)
        def send_command(self, cmd):
            return "NXOS_VERSION_12.0"
        def disconnect(self):
            pass
    monkeypatch.setattr("netmiko.ConnectHandler", FakeConn, raising=False)
    from nxos_workers import real_netmiko_worker
    host = {'host': 'rtr1', 'ip': '10.0.0.1', 'username': 'admin', 'password': 'secret'}
    cfg = 'interface Gi0/1\n no shutdown'
    res = real_netmiko_worker(host, cfg)
    assert res['status'] == 'success'
    assert 'output' in res
