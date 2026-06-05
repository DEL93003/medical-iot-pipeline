import os
import sys
import time
import requests
import random
import signal

base_gateway_url = os.getenv("GATEWAY_URL", "http://wms_gateway_server:5000")
telemetry_url = f"{base_gateway_url}/api/v1/telemetry"
firmware_check_url = f"{base_gateway_url}/api/v1/firmware/check"

# 1. Boot Sync Checklist
initial_firmware = "v1.0.0"
print("Syncing with active database state layer...", flush=True)

for _ in range(10):
    try:
        res = requests.get(firmware_check_url, timeout=2)
        if res.status_code == 200:
            initial_firmware = res.json().get("target_version", "v1.0.0")
            print(f"Boot sync complete. Operational baseline set to: {initial_firmware}", flush=True)
            break
    except Exception:
        time.sleep(2)

devices = [
    {"serial_number": "WMS-X101", "zone": "North-Wing", "firmware": initial_firmware},
    {"serial_number": "WMS-Y202", "zone": "South-ICU", "firmware": initial_firmware},
    {"serial_number": "WMS-Z303", "zone": "West-Surgery", "firmware": initial_firmware}
]

running = True

def handle_shutdown(signum, frame):
    global running
    running = False

signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)

# 2. Dynamic Operational Execution Loop
while running:
    # Fetch the live target version directly from the network endpoint each tick
    target_version = "v1.0.0"
    try:
        res = requests.get(firmware_check_url, timeout=2)
        if res.status_code == 200:
            target_version = res.json().get("target_version", "v1.0.0")
    except Exception:
        pass

    for dev in devices:
        if not running:
            break
            
        if dev["firmware"].lower() != target_version.lower():
            print(f"[{dev['serial_number']}] Updating firmware state to {target_version}...", flush=True)
            dev["firmware"] = target_version

        payload = {
            "serial_number": dev["serial_number"],
            "zone": dev["zone"],
            "firmware": dev["firmware"],
            "motor_state": random.choice(["Running", "Idle", "Calibrating"]),
            "filter_status": random.choice(["Optimal", "Good", "Replacement Required"]),
            "fluid_volume": round(random.uniform(1.2, 5.0), 2),
            "vacuum_pressure": round(random.uniform(15.5, 29.2), 1)
        }
        
        try:
            requests.post(telemetry_url, json=payload, timeout=2)
        except Exception:
            pass
            
    for _ in range(20):
        if not running:
            break
        time.sleep(0.1)

sys.exit(0)
