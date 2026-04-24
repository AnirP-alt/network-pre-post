#!/usr/bin/env python3
"""Demo: full Phase 3 flow using a mocked Netmiko but wired to the real worker interface.

This script demonstrates running the end-to-end Phase 3 flow using a mocked Netmiko
ConnectHandler so no real devices are touched. It shows how to wire a real per-host
worker implementation into the existing orchestration via set_phase3_worker.
"""
import sys
import types

# Patch Netmiko to a fake implementation so we can demonstrate end-to-end flow without devices
fake_netmiko = types.ModuleType("netmiko")
class _FakeConn:
    def __init__(self, *args, **kwargs):
        pass
    def send_config_set(self, cmds):
        return "mock-config-applied: " + ";".join(cmds)
    def send_command(self, cmd):
        return "mock-version NXOS-12.0"
    def disconnect(self):
        pass
fake_netmiko.ConnectHandler = _FakeConn
sys.modules["netmiko"] = fake_netmiko

from nxos_config_diff_phase3 import phase3_apply_inventory, set_phase3_worker
from nxos_workers import real_netmiko_worker

# Wire the real Netmiko worker into Phase 3 orchestration
set_phase3_worker(real_netmiko_worker)

inventory = '[{"host": "rtr-demo", "ip": "10.0.0.99", "username": "admin", "password": "secret"}]'
cfg = 'interface Gi0/1\n  no shutdown'
print(phase3_apply_inventory(inventory, cfg))
