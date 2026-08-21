import json
import logging
import os
import random
import ssl
import time
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

MQTT_HOST = os.getenv("MQTT_HOST", "iot_broker")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USER = os.getenv("MQTT_USER", "wms_device")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "device_secure_pass")
CA_CERT_PATH = os.getenv("CA_CERT_PATH", "/app/certs/ca.crt")

DEVICES = [
    {"serial": "WMS-OR-01", "zone": "OR-1", "firmware": "v2.1.0"},
    {"serial": "WMS-OR-02", "zone": "OR-2", "firmware": "v2.1.0"},
    {"serial": "WMS-ICU-01", "zone": "ICU-North", "firmware": "v2.0.4"},
    {"serial": "WMS-ED-01", "zone": "ED-Trauma", "firmware": "v2.2.0"}
]

client = mqtt.Client(client_id="medical_wms_simulator")
client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

if os.path.exists(CA_CERT_PATH):
    client.tls_set(ca_certs=CA_CERT_PATH, tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.tls_insecure_set(True)

def run_simulator():
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, 60)
            break
        except Exception as e:
            logging.error(f"Connection failed: {e}. Retrying in 3s...")
            time.sleep(3)

    client.loop_start()

    while True:
        for dev in DEVICES:
            payload = {
                "serial_number": dev["serial"],
                "zone": dev["zone"],
                "firmware": dev["firmware"],
                "motor_state": "RUNNING" if random.random() > 0.1 else "STANDBY",
                "filter_status": "Good" if random.random() > 0.05 else "Replacement Required",
                "vacuum_pressure": round(random.uniform(120.0, 180.0), 1),
                "fluid_volume": round(random.uniform(0.5, 4.0), 2)
            }
            topic = f"hospital/devices/{dev['serial']}/telemetry"
            client.publish(topic, json.dumps(payload))
            logging.info(f"Published telemetry to {topic}")
        time.sleep(3)

if __name__ == "__main__":
    run_simulator()
