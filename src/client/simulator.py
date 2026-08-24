import json
import logging
import os
import random
import ssl
import sys
import time
import paho.mqtt.client as mqtt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

MQTT_HOST = os.getenv("MQTT_HOST", "iot_broker")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USER = os.getenv("MQTT_USER", "wms_device")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "device_secure_pass")
CA_CERT_PATH = os.getenv("CA_CERT_PATH", "/app/certs/ca.crt")

DEVICES = [
    {"serial": "WMS-OR-01", "zone": "OR-1", "firmware": "v2.1.0", "motor_state": "RUNNING"},
    {"serial": "WMS-OR-02", "zone": "OR-2", "firmware": "v2.1.0", "motor_state": "RUNNING"},
    {"serial": "WMS-ICU-01", "zone": "ICU-North", "firmware": "v2.0.4", "motor_state": "RUNNING"},
    {"serial": "WMS-ED-01", "zone": "ED-Trauma", "firmware": "v2.2.0", "motor_state": "RUNNING"},
]

def on_connect(client, userdata, flags, reason_code, properties=None):
    logging.info(f"Simulator connected to MQTT Broker (Code: {reason_code})")

def run_simulator():
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="wms_simulator_device_client"
    )
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

    if os.path.exists(CA_CERT_PATH):
        logging.info(f"Simulator using CA Cert: {CA_CERT_PATH}")
        client.tls_set(ca_certs=CA_CERT_PATH, tls_version=ssl.PROTOCOL_TLS_CLIENT)
        client.tls_insecure_set(True)
    else:
        logging.warning(f"CA Cert NOT found at {CA_CERT_PATH} - attempting plain TLS")
        client.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)
        client.tls_insecure_set(True)

    client.on_connect = on_connect
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()

    try:
        while True:
            for dev in DEVICES:
                vac_pressure = round(random.uniform(120.0, 180.0), 1)
                payload = {
                    "serial_number": dev["serial"],
                    "zone": dev["zone"],
                    "firmware": dev["firmware"],
                    "motor_state": dev["motor_state"],
                    "filter_status": "Good" if random.random() > 0.05 else "Replacement Required",
                    "vacuum_pressure": vac_pressure,
                    "fluid_volume": round(random.uniform(0.5, 4.0), 2)
                }
                topic = f"hospital/devices/{dev['serial']}/telemetry"
                client.publish(topic, json.dumps(payload), qos=0)
                logging.info(f"Published: {dev['serial']} [{dev['motor_state']}] - {vac_pressure} kPa")
            time.sleep(3)
    except KeyboardInterrupt:
        logging.info("Stopping simulator...")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    run_simulator()
