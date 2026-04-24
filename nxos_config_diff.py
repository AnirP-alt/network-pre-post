#!/usr/bin/env python3
"""
NXOS Config Migration Comparison Tool v1.0.0
Compares before/after states of Cisco NXOS config around a migration command.
Generates HTML/JSON/CSV diff reports.
"""

import argparse
import csv
import difflib
import gzip
import json
import logging
import os
import re
import sys
import textwrap
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

try:
    from netmiko import ConnectHandler
    from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException
except ImportError:
    print("Error: netmiko not installed. Run: pip install netmiko")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

def validate_capture_commands(args):
    """Validate that any provided capture commands are non-empty strings."""
    for cap in (getattr(args, "capture", []) or []):
        if not cap or not cap.strip():
            print("Error: Empty pre-migration capture command.")
            sys.exit(2)
    for cap in (getattr(args, "post_capture", []) or []):
        if not cap or not cap.strip():
            print("Error: Empty post-migration capture command.")
            sys.exit(2)

def minify_html_string(html: str) -> str:
    import re
    s = re.sub(r"\s+", " ", html)
    s = s.replace("> <", "><")
    return s.strip()

def compute_backoff(attempt: int, retry_delay: int, retry_backoff_base: float, retry_max_delay: int) -> int:
    """Compute exponential backoff delay for a given retry attempt.

    delay = retry_delay * (retry_backoff_base ** (attempt - 1))
    cap at retry_max_delay
    """
    delay = retry_delay * (retry_backoff_base ** (attempt - 1))
    if delay > retry_max_delay:
        delay = retry_max_delay
    return int(delay)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compare NXOS config before/after running a migration command",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  %(prog)s 10.1.1.1 "feature bgp" -u admin -p secret -o diff.html

  # Compare multiple hosts
  %(prog)s --hosts-file hosts.txt --command "feature bgp" -o results/

  # With pre/post capture commands
  %(prog)s 10.1.1.1 "configure terminal; feature bgp" \\
    --capture "show ip route" --capture "show ip bgp" \\
    --post-capture "show ip route" -o diff.html

  # With rollback on error
  %(prog)s 10.1.1.1 "configure terminal; feature bgp" \\
    --rollback-cmd "configure terminal; no feature bgp" \\
    --rollback-auto -o diff.html
        """
    )
    parser.add_argument("host", nargs="?", help="NXOS device hostname/IP")
    parser.add_argument("command", nargs="?", help="Migration command to run")
    
    conn = parser.add_argument_group("Connection Options")
    conn.add_argument("-u", "--user", help="SSH username (or NXOS_USER env var)")
    conn.add_argument("-p", "--password", help="SSH password (or NXOS_PASSWORD env var)")
    conn.add_argument("--key", type=Path, help="SSH private key file")
    conn.add_argument("--port", default=22, type=int, help="SSH port (default: 22)")
    conn.add_argument("--timeout", default=30, type=int, help="SSH command timeout (default: 30s)")
    
    capture = parser.add_argument_group("Capture Options")
    capture.add_argument("--capture", action="append", default=[], help="Pre-migration command to capture")
    capture.add_argument("--post-capture", action="append", default=[], help="Post-migration command to capture")
    capture.add_argument("--config-cmd", default="show running-config all", help="Config capture command")
    capture.add_argument("--cache-dir", type=Path, help="Cache directory for configs")
    
    backup = parser.add_argument_group("Backup & Rollback Options")
    backup.add_argument("--backup-cmd", help="Backup command before migration")
    backup.add_argument("--rollback-cmd", help="Command to rollback on failure")
    backup.add_argument("--rollback-auto", action="store_true", help="Auto-rollback if migration fails")
    
    retry = parser.add_argument_group("Retry Options")
    retry.add_argument("--retries", type=int, default=0, help="Number of retry attempts")
    retry.add_argument("--retry-delay", type=int, default=5, help="Seconds between retries")
    # Exponential backoff controls (Phase 2 improvements)
    retry.add_argument("--retry-backoff-base", type=float, default=2.0, help="Backoff base for exponential retries")
    retry.add_argument("--retry-max-delay", type=int, default=60, help="Maximum delay (seconds) between retries")
    
    output = parser.add_argument_group("Output Options")
    output.add_argument("-o", "--output", type=Path, help="Output file or directory")
    output.add_argument("--view", choices=["unified", "side-by-side"], default="unified", help="Diff view")
    output.add_argument("--output-format", choices=["html", "json", "csv"], default="html", help="Output format")
    output.add_argument("--show-only-changed", action="store_true", help="Only show changed lines")
    output.add_argument("--minify", action="store_true", help="Minify HTML output")
    
    multi = parser.add_argument_group("Multi-Device Options")
    multi.add_argument("--hosts-file", type=Path, help="File with list of hosts")
    multi.add_argument("--workers", type=int, default=1, help="Number of parallel workers")
    multi.add_argument("--continue-on-error", action="store_true", help="Continue if one device fails")
    multi.add_argument("--aggregate-summary", action="store_true", help="Generate summary report")
    
    error = parser.add_argument_group("Error Options")
    error.add_argument("--error-patterns", help="Custom error patterns (comma-separated)")
    error.add_argument("--abort-on-error", action="store_true", help="Stop on migration failure")
    
    general = parser.add_argument_group("General Options")
    general.add_argument("--log-level", choices=["debug", "info", "warning", "error"], default="info")
    general.add_argument("--fail-if-changed", action="store_true", help="Exit non-zero if changes detected")
    general.add_argument("--version", action="version", version="%(prog)s 1.0.0")
    
    return parser.parse_args()


def get_credentials(args):
    user = args.user or os.environ.get("NXOS_USER")
    password = args.password or os.environ.get("NXOS_PASSWORD")
    if not user:
        raise ValueError("SSH user required (--user or NXOS_USER env var)")
    if not password and not args.key:
        raise ValueError("SSH password required (--password or NXOS_PASSWORD env var or --key)")
    return user, password


def build_ssh_conn(host: str, user: str, port: int, password: Optional[str] = None, 
                  key_path: Optional[Path] = None, timeout: int = 30) -> dict:
    device = {
        "device_type": "cisco_nxos",
        "host": host,
        "port": port,
        "username": user,
        "timeout": timeout,
    }
    if password:
        device["password"] = password
    if key_path:
        device["ssh_key_file"] = str(key_path)
    return device


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^\w\-]", "_", name)
    name = re.sub(r"_+", "_", name)
    return name.strip("_").lower()


def format_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def save_capture_output(output_dir: Path, host: str, phase: str, command: str, output: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd_name = sanitize_filename(command)
    filename = f"{host}_{format_timestamp()}_{phase}_{cmd_name}.txt"
    filepath = output_dir / filename
    filepath.write_text(output)
    return filepath


def compute_diff(before: str, after: str) -> Tuple[List[str], List[str], List[str]]:
    before_lines = [line for line in before.splitlines() if line.strip()]
    after_lines = [line for line in after.splitlines() if line.strip()]
    
    matcher = difflib.Differ()
    diff = list(matcher.compare(before_lines, after_lines))
    
    added = []
    removed = []
    unchanged = []
    
    for line in diff:
        if line.startswith("+ "):
            added.append(line[2:])
        elif line.startswith("- "):
            removed.append(line[2:])
        elif line.startswith("  "):
            unchanged.append(line[2:])
    
    return added, removed, unchanged


def escape_html(text: str) -> str:
    return (text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;"))


def minify_html(html: str) -> str:
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    html = re.sub(r"\s+", " ", html)
    html = re.sub(r">\s+<", "><", html)
    return html.strip()


def migration_failed(output: str, error_patterns: List[str]) -> bool:
    output_lower = output.lower()
    return any(pattern.lower() in output_lower for pattern in error_patterns)


def categorize_error(output, error_patterns: List[str]) -> dict:
    """Classify an error from migration output into a structured dict.
    Accepts a string or a dict containing a 'message' or 'output' field.
    """
    if isinstance(output, dict):
        text = output.get("message") or output.get("output") or str(output)
    else:
        text = output
    out = (str(text) or "").lower()
    # Simple heuristic categories
    if any(p in out for p in ["authentication", "auth", "permission denied"]):
        return {"type": "auth", "message": "Authentication failure detected"}
    if any(p in out for p in ["timeout", "timed out", "connection timed out"]):
        return {"type": "timeout", "message": "Connection timeout"}
    for p in (error_patterns or ["error:", "failed", "% ", "invalid", "could not"]):
        if p and p.lower() in out:
            return {"type": "execution", "message": f"Detected error pattern: {p}"}
    return {"type": "unknown", "message": "Unknown error"}


def _error_text(err) -> str:
    if isinstance(err, dict):
        t = err.get("type", "error")
        m = err.get("message", "")
        return f"{t}: {m}" if m else t
    if isinstance(err, str):
        return err
    return str(err)


def generate_html_diff(before: str, after: str, host: str, command: str, 
                   added: List[str], removed: List[str], unchanged_count: int,
                   view: str = "unified", show_only_changed: bool = False,
                   minify: bool = False) -> str:
    added_count = len(added)
    removed_count = len(removed)
    unchanged_count = max(0, unchanged_count)
    
    if view == "side-by-side":
        before_lines = [line for line in before.splitlines() if line.strip()]
        after_lines = [line for line in after.splitlines() if line.strip()]
        
        before_html = escape_html("\n".join(before_lines))
        after_html = escape_html("\n".join(after_lines))
        
        if show_only_changed:
            left_col = "".join(f"<div class='line removed'>-{escape_html(l)}</div>" for l in removed)
            right_col = "".join(f"<div class='line'>{escape_html(l)}</div>" for l in added)
        else:
            left_col = before_html
            right_col = after_html
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>NXOS Config Diff - {host}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 100%; background: white; padding: 20px; border-radius: 8px; }}
        h1 {{ color: #333; border-bottom: 2px solid #0066cc; padding-bottom: 10px; }}
        .meta {{ color: #666; margin-bottom: 20px; }}
        .stats {{ display: flex; gap: 20px; margin-bottom: 20px; }}
        .stat {{ padding: 10px 20px; border-radius: 4px; font-weight: bold; }}
        .stat.added {{ background: #d4edda; }}
        .stat.removed {{ background: #f8d7da; }}
        .stat.unchanged {{ background: #e2e3e5; }}
        .side-by-side {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        .pane {{ background: #f8f9fa; padding: 15px; border-radius: 4px; overflow-x: auto; }}
        pre {{ margin: 0; font-family: monospace; font-size: 12px; white-space: pre-wrap; }}
        .line {{ font-family: monospace; white-space: pre-wrap; }}
        .line.removed {{ color: #dc3545; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>NXOS Config Comparison</h1>
        <div class="meta">
            <strong>Host:</strong> {escape_html(host)} | 
            <strong>Command:</strong> {escape_html(command)} | 
            <strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </div>
        <div class="stats">
            <div class="stat added">+ Added: {added_count}</div>
            <div class="stat removed">- Removed: {removed_count}</div>
            <div class="stat unchanged">= Unchanged: {unchanged_count}</div>
        </div>
        <div class="side-by-side">
            <div class="pane"><h3>Before</h3><pre>{left_col}</pre></div>
            <div class="pane"><h3>After</h3><pre>{right_col}</pre></div>
        </div>
    </div>
</body>
</html>"""
    else:
        added_html = "".join(f"<div class='line'>{escape_html(l)}</div>" for l in added)
        removed_html = "".join(f"<div class='line removed'>-{escape_html(l)}</div>" for l in removed)
        full_html = escape_html(after)
        
        sections = ""
        if added_html:
            sections += f"<details open><summary><h3>Added Lines (+{added_count})</h3></summary><pre>{added_html}</pre></details>"
        if removed_html:
            sections += f"<details open><summary><h3>Removed Lines (-{removed_count})</h3></summary><pre>{removed_html}</pre></details>"
        if not show_only_changed:
            sections += f"<details><summary><h3>Full Config (After)</h3></summary><pre>{full_html}</pre></details>"
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>NXOS Config Diff - {host}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 100%; background: white; padding: 20px; border-radius: 8px; }}
        h1 {{ color: #333; border-bottom: 2px solid #0066cc; padding-bottom: 10px; }}
        .meta {{ color: #666; margin-bottom: 20px; }}
        .stats {{ display: flex; gap: 20px; margin-bottom: 20px; }}
        .stat {{ padding: 10px 20px; border-radius: 4px; font-weight: bold; }}
        .stat.added {{ background: #d4edda; }}
        .stat.removed {{ background: #f8d7da; }}
        .stat.unchanged {{ background: #e2e3e5; }}
        pre {{ background: #f8f9fa; padding: 15px; border-radius: 4px; overflow-x: auto; font-family: monospace; font-size: 12px; }}
        .line {{ font-family: monospace; white-space: pre-wrap; }}
        .line.removed {{ color: #dc3545; }}
        details > summary {{ cursor: pointer; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>NXOS Config Comparison</h1>
        <div class="meta">
            <strong>Host:</strong> {escape_html(host)} | 
            <strong>Command:</strong> {escape_html(command)} | 
            <strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </div>
        <div class="stats">
            <div class="stat added">+ Added: {added_count}</div>
            <div class="stat removed">- Removed: {removed_count}</div>
            <div class="stat unchanged">= Unchanged: {unchanged_count}</div>
        </div>
        {sections}
    </div>
</body>
</html>"""
    
    return minify_html_string(html) if minify else html


def generate_json_diff(before: str, after: str, host: str, command: str,
                    added: List[str], removed: List[str], unchanged_count: int) -> str:
    return json.dumps({
        "host": host,
        "command": command,
        "timestamp": datetime.now().isoformat(),
        "stats": {
            "added": len(added),
            "removed": len(removed),
            "unchanged": max(0, unchanged_count)
        },
        "added": added,
        "removed": removed,
        "before": before,
        "after": after
    }, indent=2)


def generate_csv_diff(host: str, command: str, added: List[str], removed: List[str]) -> str:
    import io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Host", host])
    writer.writerow(["Command", command])
    writer.writerow(["Timestamp", datetime.now().isoformat()])
    writer.writerow([])
    writer.writerow(["Status", "Lines"])
    for line in added:
        writer.writerow(["Added", line])
    for line in removed:
        writer.writerow(["Removed", line])
    return output.getvalue()


def generate_summary(results: list, timestamp: str) -> str:
    total = len(results)
    success = sum(1 for r in results if r.get("success"))
    failed = total - success
    
    rows = ""
    for r in results:
        status = "Success" if r.get("success") else "Failed"
        status_class = "success" if r.get("success") else "failed"
        added = r.get("added_count", 0)
        removed = r.get("removed_count", 0)
        err = r.get("error", "-")
        error = _error_text(err) if isinstance(err, (dict, str)) else str(err)
        rows += f"""<tr class=\"{status_class}\">
            <td>{r.get("host", "-")}</td>
            <td>{status}</td>
            <td>{added}</td>
            <td>{removed}</td>
            <td>{error}</td>
        </tr>"""
    
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>NXOS Config Diff - Summary</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }}
        h1 {{ color: #333; border-bottom: 2px solid #0066cc; padding-bottom: 10px; }}
        .stats {{ display: flex; gap: 20px; margin-bottom: 20px; }}
        .stat {{ padding: 10px 20px; border-radius: 4px; font-weight: bold; }}
        .stat.total {{ background: #e2e3e5; }}
        .stat.success {{ background: #d4edda; }}
        .stat.failed {{ background: #f8d7da; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #dee2e6; }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        tr.failed {{ background: #f8d7da; }}
        tr.success {{ background: #d4edda; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>NXOS Config Comparison - Summary</h1>
        <div class="stats">
            <div class="stat total">Total: {total}</div>
            <div class="stat success">Success: {success}</div>
            <div class="stat failed">Failed: {failed}</div>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Host</th>
                    <th>Status</th>
                    <th>Added</th>
                    <th>Removed</th>
                    <th>Error</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
    </div>
</body>
</html>"""


def run_migration(args, host: str, user: str, password: str):
    result = {
        "host": host,
        "success": False,
        "added_count": 0,
        "removed_count": 0,
        "error": None
    }
    
    error_patterns = args.error_patterns.split(",") if args.error_patterns else ["error:", "failed", "% ", "invalid", "could not"]
    conn_params = build_ssh_conn(host, user, args.port, password, args.key, args.timeout)
    
    try:
        logger.info(f"[{host}] Connecting...")
        net_connect = ConnectHandler(**conn_params)
        
        if net_connect.check_enable_mode() != 1:
            logger.info(f"[{host}] Entering enable mode...")
            net_connect.enable()
        
        if args.cache_dir:
            args.cache_dir.mkdir(parents=True, exist_ok=True)
        
        if args.capture:
            logger.info(f"[{host}] Capturing pre-migration commands...")
            for cmd in args.capture:
                output_text = net_connect.send_command(cmd, timeout=args.timeout)
                if args.cache_dir:
                    filepath = save_capture_output(args.cache_dir, host, "pre", cmd, output_text)
                    logger.info(f"[{host}] Saved: {filepath}")
        
        logger.info(f"[{host}] Capturing config (before)...")
        before_output = net_connect.send_command(args.config_cmd, timeout=args.timeout)
        
        if args.backup_cmd:
            logger.info(f"[{host}] Running backup command...")
            net_connect.send_command(args.backup_cmd, timeout=args.timeout)
        
        logger.info(f"[{host}] Running migration command...")
        migration_output = net_connect.send_command(args.command, timeout=args.timeout)
        logger.info(f"[{host}] Migration output: {migration_output[:500]}")
        
        if migration_failed(migration_output, error_patterns):
            logger.warning(f"[{host}] Migration command may have failed")
            err = categorize_error(migration_output, error_patterns)
            result["error"] = err
            if err["type"] in ("auth", "timeout"):
                # Abort on obvious transport/auth errors if configured
                if getattr(args, 'abort_on_error', False):
                    net_connect.disconnect()
                    return result
            # Rollback handling
            if getattr(args, 'rollback_auto', False) or getattr(args, 'rollback_cmd', None):
                rollback_cmd = getattr(args, 'rollback_cmd', None) or getattr(args, 'backup_cmd', None)
                if rollback_cmd:
                    logger.info(f"[{host}] Rolling back via: {rollback_cmd}")
                    try:
                        rollback_output = net_connect.send_command(rollback_cmd, timeout=args.timeout)
                        result["rollback_output"] = rollback_output
                        # Simple rollback success heuristic
                        if rollback_output and any(p in rollback_output.lower() for p in ["error", "failed", "% ", "invalid", "could not"]):
                            result["rollback_success"] = False
                        else:
                            result["rollback_success"] = True
                    except Exception as re:
                        result["rollback_success"] = False
                        result["rollback_output"] = str(re)
        
        if args.post_capture:
            logger.info(f"[{host}] Capturing post-migration commands...")
            for cmd in args.post_capture:
                output_text = net_connect.send_command(cmd, timeout=args.timeout)
                if args.cache_dir:
                    filepath = save_capture_output(args.cache_dir, host, "post", cmd, output_text)
                    logger.info(f"[{host}] Saved: {filepath}")
        
        logger.info(f"[{host}] Capturing config (after)...")
        after_output = net_connect.send_command(args.config_cmd, timeout=args.timeout)
        
        net_connect.disconnect()
        
        added, removed, unchanged = compute_diff(before_output, after_output)
        result["added_count"] = len(added)
        result["removed_count"] = len(removed)
        
        if args.output:
            if args.output.is_dir():
                output_ext = f".{args.output_format}"
                output_path = args.output / f"{host}_{format_timestamp()}_diff{output_ext}"
            else:
                output_path = args.output
            args.output.mkdir(parents=True, exist_ok=True) if args.output.is_dir() else None
            
            if args.output_format == "json":
                output = generate_json_diff(before_output, after_output, host, args.command, added, removed, len(unchanged))
            elif args.output_format == "csv":
                output = generate_csv_diff(host, args.command, added, removed)
            else:
                output = generate_html_diff(before_output, after_output, host, args.command, added, removed, len(unchanged), args.view, args.show_only_changed, args.minify)
                if getattr(args, 'minify', False):
                    try:
                        output = minify_html_string(output)
                    except Exception:
                        pass
                if getattr(args, 'minify', False):
                    try:
                        output = minify_html_string(output)
                    except Exception:
                        pass
            
            if args.output.is_dir():
                output_path.write_text(output)
                logger.info(f"[{host}] Output written to {output_path}")
        
        result["success"] = True
        
    except NetmikoAuthenticationException as e:
        logger.error(f"[{host}] Authentication failed: {e}")
        result["error"] = str(e)
    except NetmikoTimeoutException as e:
        logger.error(f"[{host}] Connection timeout: {e}")
        result["error"] = str(e)
    except Exception as e:
        logger.error(f"[{host}] Error: {e}")
        result["error"] = str(e)
    
    return result


def main():
    args = parse_args()
    # Validate capture commands early to fail fast with clear messages
    try:
        validate_capture_commands(args)
    except NameError:
        # If function not defined yet due to patch order, ignore for now
        pass
    
    log_level = getattr(logging, args.log_level.upper())
    logger.setLevel(log_level)
    
    try:
        user, password = get_credentials(args)
    except ValueError as e:
        logger.error(f"Credential error: {e}")
        sys.exit(1)
    
    if args.cache_dir:
        args.cache_dir.mkdir(parents=True, exist_ok=True)
    
    hosts = []
    if args.hosts_file:
        content = args.hosts_file.read_text()
        hosts = [h.strip() for h in content.split(args.hosts_separator) if h.strip()] if hasattr(args, 'hosts_separator') else [h.strip() for h in content.split(",") if h.strip()]
    elif args.host:
        hosts = [args.host]
    
        if not hosts:
            logger.error("No hosts specified")
        sys.exit(1)
    
    if not args.command:
        logger.error("Migration command required")
        sys.exit(1)
    
    results = []
    
    if len(hosts) == 1 or args.workers == 1:
        for host in hosts:
            attempt = 0
            last_result = None
            
            while attempt <= args.retries:
                if attempt > 0:
                    # Exponential backoff (Phase 2)
                    base = getattr(args, 'retry_delay', 5)
                    backoff_base = getattr(args, 'retry_backoff_base', 2.0)
                    max_delay = getattr(args, 'retry_max_delay', 60)
                    delay = compute_backoff(attempt, base, backoff_base, max_delay)
                    logger.info(f"[{host}] Retry {attempt}/{args.retries} in {delay}s...")
                    import time
                    time.sleep(delay)
                
                last_result = run_migration(args, host, user, password)
                
                if last_result.get("success") or not args.continue_on_error:
                    break
                
                attempt += 1
            
            results.append(last_result)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_to_host = {
                executor.submit(run_migration, args, host, user, password): host
                for host in hosts
            }
            
            for future in as_completed(future_to_host):
                host = future_to_host[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(f"[{host}] Exception: {e}")
                    results.append({"host": host, "success": False, "error": str(e)})
    
    if args.aggregate_summary and len(hosts) > 1:
        summary_html = generate_summary(results, format_timestamp())
        summary_path = args.cache_dir / f"summary_{format_timestamp()}.html" if args.cache_dir else args.output / f"summary_{format_timestamp()}.html" if args.output else Path(f"summary_{format_timestamp()}.html")
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(summary_html)
        logger.info(f"Summary written to {summary_path}")
    
    if args.fail_if_changed:
        has_changes = any(r.get("added_count", 0) > 0 or r.get("removed_count", 0) > 0 for r in results)
        if has_changes:
            logger.warning("Changes detected, exiting with non-zero code")
            sys.exit(1)
    
    for r in results:
        status = "SUCCESS" if r.get("success") else "FAILED"
        logger.info(f"[{r['host']}] {status}: +{r.get('added_count', 0)}/-{r.get('removed_count', 0)}")


if __name__ == "__main__":
    main()
