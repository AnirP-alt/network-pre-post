"""Demo: Logging hooks for Phase 4.

Shows how to use the logging helpers and how to weave them into a workflow.
"""

from nxos_config_logs import write_host_log, write_fleet_log

def demo():
  host = {'host': 'rtr-demo', 'ip': '10.0.0.99'}
  host_log = write_host_log(host, 'config applied: Gi0/1', base_dir='logs_demo')
  fleet_log = write_fleet_log('phase4: fleet activity', base_dir='logs_demo')
  print(host_log)
  print(fleet_log)

if __name__ == '__main__':
  demo()
