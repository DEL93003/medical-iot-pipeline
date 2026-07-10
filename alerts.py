import os
import sys
import requests

# Color formatting helpers for the container logs
GREEN = "\033[92m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

def dispatch_critical_alert(device_serial, zone, condition_type, current_value):
    """
    Handles event-driven dispatching for hardware warnings.
    Broadcasts a live network webhook to the downstream ticketing microservice.
    """
    print(f"\n{RED}{BOLD}[ALERT ENGINE] 🚨 CRITICAL HARDWARE STATE DETECTED{RESET}")
    print(f"==================================================")
    print(f"• Target Node:  {device_serial}")
    print(f"• Facility Zone: {zone}")
    print(f"• Condition:     {condition_type}")
    print(f"• Metric Value:  {current_value}")
    print(f"==================================================")
    
    payload = {
        "device_serial": device_serial,
        "zone": zone,
        "condition": condition_type,
        "value": current_value
    }
    
    # Read destination host from environment (Docker service name), defaulting to localhost for local testing
    ticketing_host = os.environ.get("TICKETING_HOST", "ticketing_service")
    webhook_url = f"http://{ticketing_host}:6000/webhook"
    
    try:
        response = requests.post(webhook_url, json=payload, timeout=2)
        print(f"{GREEN}[ALERT ENGINE] Broadcasted live webhook to consumer -> Status: {response.status_code}{RESET}")
    except Exception as network_err:
        print(f"{RED}[ALERT ENGINE ERROR] Webhook delivery failed: {network_err}{RESET}")
        
    sys.stdout.flush()
    return True
