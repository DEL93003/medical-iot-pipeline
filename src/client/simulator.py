import os
import sys
import time
import requests
import random
import signal

base_gateway_url = os.getenv("GATEWAY_URL", "http://wms_gateway_server:5000")
auth_url = f"{base_gateway_url}/api/v1/auth/token"
telemetry_url = f"{base_gateway_url}/api/v1/telemetry"

print("Boot Sync Sequence Initiated...", flush=True)

# 🔑 Fetch a secure JWT Token on startup
jwt_token = None
for attempt in range(10):
    try:
        print(f"Requesting secure token authorization payload (Attempt {attempt+1}/10)...", flush=True)
        res = requests.post(auth_url, timeout=3)
        if res.status_code == 200:
            jwt_token = res.json().get("token")
            print("Secure JWT token acquired and cached successfully!", flush=True)
            break
    except Exception as e:
        print(f"Auth synchronization delay: {str(e)}", flush=True)
    time.sleep(2)

if not jwt_token:
    print("❌ Critical Error: Could not verify identity with backend gateway. Exiting.", flush=True)
    sys.exit(1)

devices = [
    {"serial_number": "WMS-X101", "zone": "North-Wing", "firmware": "v1.0.0"},
    {"serial_number": "WMS-Y202", "zone": "South-ICU", "firmware": "v1.0.0"},
    {"serial_number": "WMS-Z303", "zone": "West-Surgery", "firmware": "v1.0.0"}
]

running = True

def handle_shutdown(signum, frame):
    global running
    print("\nGracefully idling out device simulator cluster pipeline...", flush=True)
    running = False

signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)

print("Entering active telemetry streaming state loop.\n", flush=True)

while running:
    for dev in devices:
        # Generate some mock telemetry drift values
        if dev["serial_number"] == "WMS-Z303":
            # Keep this node triggering the hardware alerts
            filter_status = "Replacement Required"
            fluid_volume = round(random.uniform(2.60, 2.85), 2)
            vacuum_pressure = round(random.uniform(23.0, 24.5), 1)
            motor_state = "Calibrating"
        else:
            filter_status = "Good"
            fluid_volume = round(random.uniform(1.10, 2.65), 2)
            vacuum_pressure = round(random.uniform(19.5, 23.5), 1)
            motor_state = "Idle" if dev["serial_number"] == "WMS-X101" else "Calibrating"

        payload = {
            "serial_number": dev["serial_number"],
            "zone": dev["zone"],
            "firmware": dev["firmware"],
            "motor_state": motor_state,
            "filter_status": filter_status,
            "fluid_volume": fluid_volume,
            "vacuum_pressure": vacuum_pressure
        }

        try:
            # Attach the cached bearer token header to satisfy our token_required decorator
            headers = {
                "Authorization": f"Bearer {jwt_token}",
                "Content-Type": "application/json"
            }
            response = requests.post(telemetry_url, json=payload, headers=headers, timeout=2)
            print(f"[STREAM] Outbound packet {dev['serial_number']} -> Status: {response.status_code}", flush=True)
        except Exception as err:
            print(f"[STREAM ERROR] Disconnect on {dev['serial_number']}: {str(err)}", flush=True)

    time.sleep(3)
