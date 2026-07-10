import os
import sys
import time
import random
import signal
import json
import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "iot_broker")
MQTT_PORT = 1883
MQTT_TOPIC_PUB = "telemetry/devices"
MQTT_TOPIC_SUB = "commands/devices"

# Initialize local mutable memory states for our device assets
device_states = {
    "WMS-X101": {"firmware": "v1.1.0", "fluid_volume": 1.62, "filter_status": "Good"},
    "WMS-Y202": {"firmware": "v1.1.0", "fluid_volume": 1.47, "filter_status": "Good"},
    "WMS-Z303": {"firmware": "v1.1.0", "fluid_volume": 2.65, "filter_status": "Replacement Required"}
}

print("Initializing bidirectional MQTT asset node setup...", flush=True)
client = mqtt.Client()

def on_message(client, userdata, msg):
    try:
        cmd_payload = json.loads(msg.payload.decode())
        serial = cmd_payload.get("serial_number")
        action = cmd_payload.get("command")
        
        if serial in device_states:
            if action == "flush_filter":
                print(f"📥 [REMOTE COMMAND] Executing physical fluid purge on node {serial}", flush=True)
                device_states[serial]["fluid_volume"] = 0.0
                device_states[serial]["filter_status"] = "Good"
            elif action == "push_update":
                current_ver = device_states[serial]["firmware"]
                # Parse 'v1.1.0' -> increment minor/patch patch digit dynamically
                major, minor, patch = map(int, current_ver.strip("v").split("."))
                new_ver = f"v{major}.{minor}.{patch + 1}"
                print(f"📥 [REMOTE COMMAND] Flashing chip firmware on node {serial} ({current_ver} -> {new_ver})", flush=True)
                device_states[serial]["firmware"] = new_ver
    except Exception as e:
        print(f"[COMMAND ERROR] Failed to parse broker instruction: {e}", flush=True)

client.on_message = on_message

try:
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.subscribe(MQTT_TOPIC_SUB)
    client.loop_start()
    print("🚀 Bidirectional control sockets opened successfully!", flush=True)
except Exception as e:
    print(f"❌ Critical Connection Error: {str(e)}", flush=True)
    sys.exit(1)

running = True
def handle_shutdown(signum, frame):
    global running
    running = False
    client.loop_stop()
    client.disconnect()

signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)

while running:
    for serial, state in device_states.items():
        # Simulate physical accumulation based on current asset states
        if state["filter_status"] == "Replacement Required":
            state["fluid_volume"] = round(random.uniform(2.60, 2.85), 2)
            vacuum_pressure = round(random.uniform(23.0, 24.5), 1)
            motor_state = "Calibrating"
        else:
            # Gradually accumulate fluid naturally over time from its baseline
            state["fluid_volume"] = round(state["fluid_volume"] + random.uniform(0.02, 0.06), 2)
            vacuum_pressure = round(random.uniform(19.5, 22.5), 1)
            motor_state = "Idle" if serial == "WMS-X101" else "Calibrating"
            
            # Re-trigger alarm state if threshold crosses limits naturally
            if state["fluid_volume"] >= 2.50:
                state["filter_status"] = "Replacement Required"

        payload = {
            "serial_number": serial,
            "zone": "North-Wing" if serial == "WMS-X101" else "South-ICU" if serial == "WMS-Y202" else "West-Surgery",
            "firmware": state["firmware"],
            "motor_state": motor_state,
            "filter_status": state["filter_status"],
            "fluid_volume": state["fluid_volume"],
            "vacuum_pressure": vacuum_pressure
        }

        client.publish(MQTT_TOPIC_PUB, json.dumps(payload), qos=1)

    time.sleep(3)
