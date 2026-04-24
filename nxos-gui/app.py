#!/usr/bin/env python3
"""
NXOS Config Migration - Streamlit GUI
Web interface for NXOS config comparison tool.
"""

import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import streamlit as st

try:
    from netmiko import ConnectHandler
    from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException
except ImportError:
    st.error("netmiko not installed. Run: pip install netmiko")
    st.stop()

import difflib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PREDEFINED_CAPTURES = [
    "show ip route",
    "show ip bgp",
    "show ip route ospf",
    "show ip forwarding",
    "show ip forwarding ipv4 unicast",
    "show version",
    "show interface",
    "show vlan",
    "show inventory",
    "show environment",
]


def format_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def build_ssh_conn(host, user, port, password=None, timeout=30):
    device = {
        "device_type": "cisco_nxos",
        "host": host,
        "port": port,
        "username": user,
        "timeout": timeout,
    }
    if password:
        device["password"] = password
    return device


def compute_diff(before: str, after: str):
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


def migration_failed(output: str, error_patterns: list) -> bool:
    output_lower = output.lower()
    return any(pattern.lower() in output_lower for pattern in error_patterns)


def generate_html_diff(
    before: str, after: str, host: str, command: str,
    added, removed, unchanged_count: int,
    view: str = "unified", show_only_changed: bool = False
) -> str:
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
        
        return f"""<!DOCTYPE html>
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
    
    return f"""<!DOCTYPE html>
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


def run_migration(
    host, command, user, password=None,
    port=22, timeout=30,
    pre_capture=None, post_capture=None,
    config_cmd="show running-config all",
    error_patterns=None,
    view_mode="unified",
    show_only_changed=False
):
    result = {
        "host": host,
        "success": False,
        "added_count": 0,
        "removed_count": 0,
        "error": None,
        "captures": {"pre": {}, "post": {}},
        "html": None
    }
    
    if error_patterns is None:
        error_patterns = ["error:", "failed", "% ", "invalid", "could not"]
    
    conn_params = build_ssh_conn(host, user, port, password, timeout)
    
    try:
        logger.info(f"Connecting to {host}...")
        net_connect = ConnectHandler(**conn_params)
        
        if net_connect.check_enable_mode() != 1:
            net_connect.enable()
        
        if pre_capture:
            for cmd in pre_capture:
                output = net_connect.send_command(cmd, timeout=timeout)
                result["captures"]["pre"][cmd] = output
                logger.info(f"Captured pre: {cmd}")
        
        before_output = net_connect.send_command(config_cmd, timeout=timeout)
        
        logger.info(f"Running migration on {host}...")
        migration_output = net_connect.send_command(command, timeout=timeout)
        
        if migration_failed(migration_output, error_patterns):
            result["error"] = f"Migration warning: {migration_output[:200]}"
            logger.warning(f"Migration warning: {result['error']}")
        
        if post_capture:
            for cmd in post_capture:
                output = net_connect.send_command(cmd, timeout=timeout)
                result["captures"]["post"][cmd] = output
                logger.info(f"Captured post: {cmd}")
        
        after_output = net_connect.send_command(config_cmd, timeout=timeout)
        
        net_connect.disconnect()
        
        added, removed, unchanged = compute_diff(before_output, after_output)
        result["added_count"] = len(added)
        result["removed_count"] = len(removed)
        
        result["html"] = generate_html_diff(
            before_output, after_output, host, command,
            added, removed, len(unchanged),
            view=view_mode, show_only_changed=show_only_changed
        )
        
        result["success"] = True
        
    except NetmikoAuthenticationException as e:
        result["error"] = f"Authentication failed: {e}"
        logger.error(f"{host}: {result['error']}")
    except NetmikoTimeoutException as e:
        result["error"] = f"Connection timeout: {e}"
        logger.error(f"{host}: {result['error']}")
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"{host}: {e}")
    
    return result


def main():
    st.set_page_config(
        page_title="NXOS Config Migration",
        page_icon="🔄",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("🔄 NXOS Config Migration Comparison")
    st.markdown("Compare Cisco NXOS configuration before and after migration commands")
    
    with st.sidebar:
        st.header("Connection Settings")
        
        use_env = st.checkbox("Use environment variables", 
                      value=bool(os.environ.get("NXOS_USER")))
        
        if use_env:
            env_user = os.environ.get("NXOS_USER", "")
            env_pass = os.environ.get("NXOS_PASSWORD", "")
            st.caption(f"User: {'*' * len(env_user) if env_user else '(not set)'}")
            user = env_user
            password = env_pass
        else:
            user = st.text_input("Username", placeholder="admin")
            password = st.text_input("Password", type="password")
        
        col1, col2 = st.columns(2)
        with col1:
            port = st.number_input("Port", value=22, min_value=1, max_value=65535)
        with col2:
            timeout = st.number_input("Timeout (s)", value=30, min_value=5)
        
        st.divider()
        
        st.header("Capture Options")
        
        pre_captures = st.multiselect(
            "Pre-migration commands",
            PREDEFINED_CAPTURES,
            default=["show ip route", "show ip bgp"]
        )
        
        post_captures = st.multiselect(
            "Post-migration commands",
            PREDEFINED_CAPTURES,
            default=["show ip route", "show ip bgp"]
        )
        
        custom_pre = st.text_area("Custom pre-commands (one per line)", height=80)
        custom_post = st.text_area("Custom post-commands (one per line)", height=80)
        
        if custom_pre.strip():
            pre_captures.extend([c.strip() for c in custom_pre.split("\n") if c.strip()])
        if custom_post.strip():
            post_captures.extend([c.strip() for c in custom_post.split("\n") if c.strip()])
        
        config_cmd = st.text_input("Config command", value="show running-config all")
    
    tab1, tab2 = st.tabs(["Single Device", "Multi-Device"])
    
    with tab1:
        host = st.text_input("Host/IP", placeholder="10.1.1.1")
        
        command = st.text_area(
            "Migration Command",
            height=100,
            placeholder="configure terminal; feature bgp"
        )
        
        col1, col2, col3 = st.columns(3)
        with col1:
            view_mode = st.selectbox("View", ["unified", "side-by-side"])
        with col2:
            show_only = st.checkbox("Show only changed")
        with col3:
            abort_on_error = st.checkbox("Abort on error")
    
    with tab2:
        host_file = st.file_uploader("Host file (one per line)", type=["txt", "csv"])
        
        workers = st.number_input("Parallel workers", value=1, min_value=1, max_value=10)
    
    run_button = st.button("🚀 Run Migration", type="primary", use_container_width=True)
    
    if run_button:
        if not user:
            st.error("Username required")
            st.stop()
        
        if not command:
            st.error("Migration command required")
            st.stop()
        
        results = []
        
        if tab1:
            if not host:
                st.error("Host required")
                st.stop()
            hosts = [host]
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, h in enumerate(hosts):
                status_text.text(f"Processing {h} ({i+1}/{len(hosts)})...")
                progress_bar.progress((i + 1) / len(hosts))
                
                result = run_migration(
                    host=h,
                    command=command,
                    user=user,
                    password=password,
                    port=port,
                    timeout=timeout,
                    pre_capture=pre_captures,
                    post_capture=post_captures,
                    config_cmd=config_cmd,
                    error_patterns=["error:", "failed", "% ", "invalid", "could not"] if not abort_on_error else None,
                    view_mode=view_mode,
                    show_only_changed=show_only
                )
                results.append(result)
        else:
            if not host_file:
                st.warning("Please upload a host file in Multi-Device tab")
                st.stop()
            
            content = host_file.getvalue().decode("utf-8")
            hosts = [h.strip() for h in content.split("\n") if h.strip()]
            
            if not hosts:
                st.error("No hosts found in file")
                st.stop()
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(
                        run_migration,
                        h, command, user, password, port, timeout,
                        pre_captures, post_captures, config_cmd,
                        ["error:", "failed", "% ", "invalid", "could not"] if not abort_on_error else None,
                        view_mode, show_only
                    ): h
                    for h in hosts
                }
                
                for i, future in enumerate(as_completed(futures)):
                    h = futures[future]
                    try:
                        result = future.result()
                    except Exception as e:
                        result = {"host": h, "success": False, "error": str(e)}
                    status_text.text(f"Processed {h} ({i+1}/{len(hosts)})...")
                    progress_bar.progress((i + 1) / len(hosts))
                    results.append(result)
        
        progress_bar.empty()
        status_text.text("Complete!")
        
        st.success(f"Processed {len(results)} device(s)")
        
        for r in results:
            with st.expander(f"{r['host']}: {'✅' if r['success'] else '❌'}", expanded=True):
                if r["success"]:
                    st.metric("Added lines", r["added_count"])
                    st.metric("Removed lines", r["removed_count"])
                    
                    if r["html"]:
                        st.subheader("Config Diff")
                        st.components.v1.html(
                            r["html"], 
                            height=600, 
                            scrolling=True
                        )
                        
                        timestamp = format_timestamp()
                        filename = f"{r['host']}_{timestamp}_diff.html"
                        st.download_button(
                            "📥 Download HTML",
                            r["html"],
                            file_name=filename,
                            mime="text/html"
                        )
                    
                    if r["captures"]["pre"]:
                        st.subheader("Pre-migration Captures")
                        for cmd, output in r["captures"]["pre"].items():
                            with st.expander(f"📄 {cmd}"):
                                st.text(output)
                    
                    if r["captures"]["post"]:
                        st.subheader("Post-migration Captures")
                        for cmd, output in r["captures"]["post"].items():
                            with st.expander(f"📄 {cmd}"):
                                st.text(output)
                else:
                    st.error(r["error"])
        
        if len(results) > 1:
            st.subheader("Summary")
            summary_data = [
                {"Host": r["host"], "Status": "Success" if r["success"] else "Failed",
                 "Added": r["added_count"], "Removed": r["removed_count"],
                 "Error": r["error"] or "-"}
                for r in results
            ]
            st.table(summary_data)
    
    with st.expander("📋 Help"):
        st.markdown("""
        **Usage:**
        1. Enter connection details in sidebar
        2. Select pre/post capture commands
        3. Enter host and migration command
        4. Click "Run Migration"
        
        **Environment Variables:**
        - `NXOS_USER` - SSH username
        - `NXOS_PASSWORD` - SSH password
        """)


if __name__ == "__main__":
    main()