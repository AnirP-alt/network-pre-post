import json
import pytest

from nxos_config_diff import (
    categorize_error,
    _error_text,
    compute_backoff,
    minify_html_string,
    generate_html_diff,
    generate_json_diff,
    generate_csv_diff,
    generate_summary,
)


def test_categorize_error_types():
    # Auth related
    for t in ["authentication failed", "auth denied", "permission denied"]:
        err = categorize_error(t, [])
        assert err["type"] in ("auth",)
        assert isinstance(err, dict)

    # Timeout related
    for t in ["timeout", "timed out", "connection timed out"]:
        err = categorize_error(t, [])
        assert err["type"] in ("timeout",)

    # Execution path when error patterns provided
    err = categorize_error("error: something went wrong", ["error:", "failed"])
    assert isinstance(err, dict)


def test_compute_backoff_values():
    # base 5, backoff 2, max 60
    assert compute_backoff(1, 5, 2.0, 60) == 5
    assert compute_backoff(2, 5, 2.0, 60) == 10
    assert compute_backoff(3, 5, 2.0, 60) == 20
    assert compute_backoff(4, 5, 2.0, 60) == 40
    assert compute_backoff(5, 5, 2.0, 60) == 60


def test_minify_html_string_basic():
    html = "<div> a  b  </div>\n"
    out = minify_html_string(html)
    assert "  " not in out


def test_html_json_csv_generation_types():
    added = ["x"]
    removed = ["y"]
    before = "cfg before"
    after = "cfg after"
    html = generate_html_diff(before, after, "host", "cmd", added, removed, 0, view="unified", show_only_changed=False)
    assert isinstance(html, str)
    js = generate_json_diff(before, after, "host", "cmd", added, removed, 0)
    assert isinstance(js, str)
    csv = generate_csv_diff("host", "cmd", added, removed)
    assert isinstance(csv, str)
