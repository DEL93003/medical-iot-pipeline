import os
import ssl
import time
import json
import random
import logging
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

MQTT_BROKER = os.getenv("MQTT_BROKER", "iot_broker")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
CA_CERT_PATH = os.getenv("CA_CERT_PATH", "/certs/ca.crt")
CLIENT_CERT_PATH = os.getenv("CLIENT_CERT_PATH", "/certs/client.crt")
CLIENT_KEY_PATH = os.getenv("CLIENT_KEY_PATH", "/certs/client.key")
MQTT_USER_FILE = os.getenv("MQTT_USER_FILE", "/run/secrets/mqtt_user")
MQTT_PASS_FILE = os.getenv("MQTT_PASS_FILE", "/run/secrets/mqtt_password")

DEVICES = [
    {"serial_number": "WMS-OR-01", "zone": "OR-1", "firmware": "v2.1.0", "motor_state": "RUNNING", "filter_status": "Good", "vacuum_pressure": 140.0, "fluid_volume": 1.2},
    {"serial_number": "WMS-OR-02", "zone": "OR-2", "firmware": "v2.1.0", "motor_state": "RUNNING", "filter_status": "Good", "vacuum_pressure": 155.0, "fluid_volume": 2.1},
    {"serial_number": "WMS-ICU-01", "zone": "ICU-North", "firmware": "v2.0.4", "motor_state": "RUNNING", "filter_status": "Good", "vacuum_pressure": 160.0, "fluid_volume": 0.8},
    {"serial_number": "WMS-ED-01", "zone": "ED-Trauma", "firmware": "v2.2.0", "motor_state": "RUNNING", "filter_status": "Good", "vacuum_pressure": 135.0, "fluid_volume": 3.1}
]


def get_secret(file_path: str, default: str = "") -> str:
    try:
        with open(file_path, "r") as f:
            return f.read().strip()
    except Exception:
        return default


def on_connect(client, userdata, flags, rc):
    logging.info(f"Simulator connected to MQTT Broker with result code {rc}")
    for dev in DEVICES:
        control_topic = f"hospital/devices/{dev['serial_number']}/control"
        client.subscribe(control_topic, qos=1)
        logging.info(f"Subscribed to control topic: {control_topic}")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        sn = payload.get("serial_number")
        cmd = payload.get("command")
        logging.info(f"[COMMAND RECEIVED] Device: {sn} -> Action: {cmd}")

        for dev in DEVICES:
            if dev["serial_number"] == sn:
                if cmd == "STOP":
                    dev["motor_state"] = "STOPPED"
                    dev["vacuum_pressure"] = 0.0
                elif cmd == "START":
                    dev["motor_state"] = "RUNNING"
                    dev["vacuum_pressure"] = random.uniform(130.0, 160.0)
                elif cmd == "PURGE_CANISTER":
                    dev["fluid_volume"] = 0.0
                    logging.info(f"[PURGE] Canister reset to 0.0 L for {sn}")
                elif cmd == "RESET_FILTER":
                    dev["filter_status"] = "Good"
                    logging.info(f"[MAINTENANCE] Filter status reset to Good for {sn}")
    except Exception as e:
        logging.error(f"Error handling control message: {e}")


def main():
    user = get_secret(MQTT_USER_FILE, os.getenv("MQTT_USER", "dale_admin"))
    password = get_secret(MQTT_PASS_FILE, os.getenv("MQTT_PASS", "admin_secure_pass"))

    client = mqtt.Client(client_id="wms_fleet_simulator", protocol=mqtt.MQTTv311)
    client.username_pw_set(username=user, password=password)

    if os.path.exists(CA_CERT_PATH):
        client.tls_set(
            ca_certs=CA_CERT_PATH,
            certfile=CLIENT_CERT_PATH if os.path.exists(CLIENT_CERT_PATH) else None,
            keyfile=CLIENT_KEY_PATH if os.path.exists(CLIENT_KEY_PATH) else None,
            tls_version=ssl.PROTOCOL_TLSv1_2
        )
        client.tls_insecure_set(True)

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_start()

    while True:
        for dev in DEVICES:
            if dev["motor_state"] == "RUNNING":
                dev["vacuum_pressure"] = max(80.0, min(220.0, dev["vacuum_pressure"] + random.uniform(-4.0, 4.0)))
                dev["fluid_volume"] = min(4.0, dev["fluid_volume"] + random.uniform(0.01, 0.03))
                if dev["fluid_volume"] >= 3.8:
                    dev["filter_status"] = "Replacement Required"

            telemetry_topic = f"hospital/devices/{dev['serial_number']}/telemetry"
            payload = {
                "serial_number": dev["serial_number"],
                "zone": dev["zone"],
                "firmware": dev["firmware"],
                "motor_state": dev["motor_state"],
                "filter_status": dev["filter_status"],
                "vacuum_pressure": round(dev["vacuum_pressure"], 2),
                "fluid_volume": round(dev["fluid_volume"], 2)
            }
            client.publish(telemetry_topic, json.dumps(payload), qos=1)

        time.sleep(3)


if __name__ == "__main__":
    main()
