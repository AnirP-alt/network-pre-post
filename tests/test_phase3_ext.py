"""Phase 3 tests: multi-device inventory parsing and coordination"""

import pytest

import nxos_config_diff as app


def test_inventory_parsing_groups_and_duplicates(tmp_path):
    # Prepare a temporary inventory file with groups and duplicates
    inventory = tmp_path / "hosts.txt"
    inventory.write_text("""
    groupA: host1, host2
    host3
    # comment line
    groupA:host2,host4
    """.strip())

    hosts = app.parse_host_inventory(inventory)
    # Expect host1, host2, host3, host4 with duplicates removed
    assert set(hosts) == {"host1", "host2", "host3", "host4"}


def test_parse_inventory_empty_and_comments():
    inventory = app.Path("/nonexistent/file")
    hosts = app.parse_host_inventory(inventory)
    assert hosts == []
