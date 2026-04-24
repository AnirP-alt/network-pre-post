from nxos_config_logs import write_host_log, write_fleet_log

def test_write_host_and_fleet_logs(tmp_path):
    host = {"host": "rtr1"}
    base = tmp_path / "logs"
    host_path = write_host_log(host, "hello world", base_dir=str(base))
    fleet_path = write_fleet_log("fleet event", base_dir=str(base))
    assert host_path.endswith('.log')
    assert fleet_path.endswith('.log')
