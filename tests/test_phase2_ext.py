import json
import pytest

import nxos_config_diff as app


def test_backoff_values_against_expected():
    # Basic sanity checks for exponential backoff helper
    assert app.compute_backoff(1, 5, 2.0, 60) == 5
    assert app.compute_backoff(2, 5, 2.0, 60) == 10
    assert app.compute_backoff(3, 5, 2.0, 60) == 20
    assert app.compute_backoff(4, 5, 2.0, 60) == 40
    assert app.compute_backoff(5, 5, 2.0, 60) == 60


def test_error_classification_and_render():
    err = app.categorize_error("Authentication failed", ["error:", "failed"])
    assert isinstance(err, dict) and err["type"] == "auth"
    render = app._error_text(err)
    assert isinstance(render, str)


def test_html_json_csv_presence():
    added = ["route1"]
    removed = ["route2"]
    before = "before-config"
    after = "after-config"
    html = app.generate_html_diff(before, after, "host", "cmd", added, removed, 1, view="unified", show_only_changed=False, minify=False)
    js = app.generate_json_diff(before, after, "host", "cmd", added, removed, 1)
    csv = app.generate_csv_diff("host", "cmd", added, removed)
    assert isinstance(html, str) and len(html) > 0
    assert isinstance(js, str) and len(js) > 0
    assert isinstance(csv, str) and len(csv) > 0
