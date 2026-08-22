import os
import time
import json
import random
import paho.mqtt.client as mqtt

broker_host = os.environ.get("MQTT_HOST", "iot_broker")
mqtt_user = os.environ.get("MQTT_USER")
mqtt_pass = os.environ.get("MQTT_PASSWORD")

client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id='medical_wms_simulator')

if mqtt_user and mqtt_pass:
    client.username_pw_set(mqtt_user, mqtt_pass)

def on_connect(client, userdata, flags, reason_code, properties=None):
    print(f"🚀 Simulator authenticated and hooked into broker channel! Reason: {reason_code}", flush=True)

client.on_connect = on_connect

print("⏳ Establishing broker socket connection...", flush=True)
while True:
    try:
        client.connect(broker_host, 1883, 60)
        break
    except Exception as e:
        print(f"⏳ Broker not ready, retrying... ({e})", flush=True)
        time.sleep(2)

# Start the dedicated internal background network thread loops natively!
client.loop_start()

devices = ["WMS-Z303", "WMS-X102", "WMS-Y504"]

print("⚡ Starting telemetry payload streaming loops...", flush=True)
while True:
    for device in devices:
        payload = {
            "serial_number": device,
            "zone": "Ventura-Lab",
            "firmware": "v2.1.0",
            "motor_state": "Operational",
            "filter_status": "Good",
            "fluid_volume": round(random.uniform(0.1, 0.95), 2),
            "vacuum_pressure": round(random.uniform(-45.0, -35.0), 1)
        }
        info = client.publish("telemetry/devices", json.dumps(payload))
        # Ensure message is placed onto the socket line securely
        info.wait_for_publish(timeout=1.0)
        print(f"📤 Published frame out for: {device}", flush=True)
    
    time.sleep(5.0)
