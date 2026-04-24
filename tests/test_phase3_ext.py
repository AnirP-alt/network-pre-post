import json
from nxos_config_diff_phase3 import parse_host_inventory, _run_on_hosts_parallel, phase3_apply_inventory

def test_parse_host_inventory_basic():
    inv = '[{"host": "rtr1", "ip": "10.0.0.1"}]'
    hosts = parse_host_inventory(inv)
    assert isinstance(hosts, list)
    assert len(hosts) == 1
    assert hosts[0]['host'] == 'rtr1'
    assert hosts[0]['ip'] == '10.0.0.1'

def test_run_on_hosts_parallel_basic():
    hosts = [{'host': 'h1'}, {'host': 'h2'}]
    def worker(h):
        return {'host': h['host'], 'status': 'ok'}
    results = _run_on_hosts_parallel(hosts, worker)
    assert len(results) == 2
    assert set(r['host'] for r in results) == {'h1', 'h2'}

def test_phase3_apply_inventory_stubbed():
    inv = '[{"host":"h1","ip":"1.2.3.4"}]'
    out = phase3_apply_inventory(inv, "interface Gi0/1\\n no shutdown")
    assert isinstance(out, list)
    for item in out:
        assert 'host' in item
        assert 'status' in item
