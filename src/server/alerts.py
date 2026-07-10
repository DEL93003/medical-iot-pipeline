import os
import sys

# Color formatting helpers for the container logs
GREEN = "\033[92m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

def dispatch_critical_alert(device_serial, zone, condition_type, current_value):
    """
    Handles event-driven dispatching for hardware warnings.
    Simulates a secure outbound integration webhook (e.g., Slack, PagerDuty, or SMTP).
    """
    print(f"\n{RED}{BOLD}[ALERT ENGINE] 🚨 CRITICAL HARDWARE STATE DETECTED{RESET}")
    print(f"==================================================")
    print(f"• Target Node:  {device_serial}")
    print(f"• Facility Zone: {zone}")
    print(f"• Condition:     {condition_type}")
    print(f"• Metric Value:  {current_value}")
    print(f"==================================================")
    
    # Simulate a webhook POST request or an SMTP dispatch loop
    print(f"{GREEN}[ALERT ENGINE] Successfully dispatched JSON payload block to downstream Webhook endpoint.{RESET}\n")
    sys.stdout.flush()
    return True
