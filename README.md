# NXOS Config Migration Comparison Tool

A comprehensive tool for comparing Cisco NXOS configuration before and after running migration commands. Generates detailed HTML, JSON, and CSV reports.

## Features

- **Pre/Post Migration Capture**: Capture route tables, BGP neighbors, and other commands before and after migration
- **Multiple Output Formats**: HTML (unified/side-by-side), JSON, CSV
- **Multi-Device Support**: Process multiple hosts in parallel
- **Cache Management**: Save captured outputs to cache directory
- **Rollback Support**: Automatic rollback on migration failure
- **Retry Logic**: Configurable retry attempts for resilience
- **Error Handling**: Custom error patterns and abort options

## Installation

```bash
pip install netmiko
```

## Quick Start

### CLI Usage

```bash
# Basic comparison
python nxos_config_diff.py 10.1.1.1 "feature bgp" -u admin -p secret -o diff.html

# With pre/post capture commands
python nxos_config_diff.py 10.1.1.1 "configure terminal; feature bgp" \
  --capture "show ip route" \
  --capture "show ip bgp" \
  --post-capture "show ip route" \
  -u admin -p secret -o diff.html

# Multi-device with parallel execution
python nxos_config_diff.py --hosts-file hosts.txt \
  --command "feature bgp" \
  --workers 4 \
  --continue-on-error \
  -o results/
```

### Environment Variables

```bash
export NXOS_USER=admin
export NXOS_PASSWORD=secret
```

Then run without credentials:
```bash
python nxos_config_diff.py 10.1.1.1 "feature bgp" -o diff.html
```

## GUI Usage (Streamlit)

```bash
cd nxos-gui
pip install -r requirements.txt
streamlit run app.py
```

Access the GUI at `http://localhost:8501`

## CLI Options

### Connection Options

| Flag | Description | Default |
|------|-------------|---------|
| `-u, --user` | SSH username | NXOS_USER env |
| `-p, --password` | SSH password | NXOS_PASSWORD env |
| `--key` | SSH private key file | - |
| `--port` | SSH port | 22 |
| `--timeout` | Command timeout (seconds) | 30 |

### Capture Options

| Flag | Description |
|------|-------------|
| `--capture` | Pre-migration command to capture (repeatable) |
| `--post-capture` | Post-migration command to capture (repeatable) |
| `--config-cmd` | Config capture command |
| `--cache-dir` | Cache directory for outputs |

### Output Options

| Flag | Description | Default |
|------|-------------|---------|
| `-o, --output` | Output file or directory | stdout |
| `--view` | Diff view | unified |
| `--output-format` | html/json/csv | html |
| `--show-only-changed` | Only show changed lines | false |
| `--minify` | Minify HTML output | false |

### Multi-Device Options

| Flag | Description | Default |
|------|-------------|---------|
| `--hosts-file` | File with hosts | - |
| `--workers` | Parallel workers | 1 |
| `--continue-on-error` | Continue on failure | false |
| `--aggregate-summary` | Generate summary | false |

### Error Options

| Flag | Description |
|------|-------------|
| `--error-patterns` | Custom error patterns (comma-separated) |
| `--abort-on-error` | Stop on migration failure |

### Retry Options

| Flag | Description | Default |
|------|-------------|---------|
| `--retries` | Number of retry attempts | 0 |
| `--retry-delay` | Seconds between retries | 5 |

### Rollback Options

| Flag | Description |
|------|-------------|
| `--backup-cmd` | Backup command before migration |
| `--rollback-cmd` | Command to rollback on failure |
| `--rollback-auto` | Auto-rollback if migration fails |

## Recommended Capture Commands

For route/BGP migrations:

```bash
--capture "show ip route"
--capture "show ip bgp"
--capture "show ip route ospf"
--capture "show ip forwarding"
--capture "show ip forwarding ipv4 unicast"
```

## Output Files

| File Type | Description |
|----------|-------------|
| `{host}_{timestamp}_pre_{command}.txt` | Pre-migration capture |
| `{host}_{timestamp}_post_{command}.txt` | Post-migration capture |
| `{host}_{timestamp}_diff.html` | HTML diff report |
| `summary_{timestamp}.html` | Multi-device summary |

## Exit Codes

| Code | Description |
|------|-------------|
| 0 | Success |
| 1 | Changes detected (with `--fail-if-changed`) |
| 2 | Error |

## Requirements

- Python 3.8+
- netmiko >= 4.0.0

## License

MIT License

## Author

NXOS Config Migration Tool v1.0.0