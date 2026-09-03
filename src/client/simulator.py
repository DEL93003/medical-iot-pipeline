import os
import ssl
import time
import json
import random
import logging
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

MQTT_BROKER = os.getenv("MQTT_HOST", os.getenv("MQTT_BROKER", "iot_broker"))
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
CA_CERT_PATH = os.getenv("CA_CERT_PATH", "/app/certs/ca.crt")
CLIENT_CERT_PATH = os.getenv("CLIENT_CERT_PATH", "/app/certs/client.crt")
CLIENT_KEY_PATH = os.getenv("CLIENT_KEY_PATH", "/app/certs/client.key")
MQTT_USER_FILE = os.getenv("MQTT_USER_FILE", "/run/secrets/mqtt_user")
MQTT_PASS_FILE = os.getenv("MQTT_PASSWORD_FILE", os.getenv("MQTT_PASS_FILE", "/run/secrets/mqtt_password"))

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


def apply_command_to_device(dev: dict, cmd: str, operator: str = ""):
    cmd_upper = (cmd or "").upper()
    sn = dev["serial_number"]

    if cmd_upper in ["RETURN_HOME", "EMERGENCY_STOP", "PARK"]:
        dev["motor_state"] = "EMERGENCY_PARKED"
        dev["vacuum_pressure"] = 0.0
        logging.warning(f"[{sn}] EMERGENCY RETURN HOME ACTIVATED by {operator or 'system'}")

    elif cmd_upper in ["PURGE_CANISTER", "RESET", "DRAIN"]:
        dev["fluid_volume"] = 0.0
        dev["motor_state"] = "RUNNING"
        dev["vacuum_pressure"] = round(random.uniform(130.0, 155.0), 2)
        dev["filter_status"] = "Good"
        logging.info(f"[{sn}] Canister drained to 0.0L & motor reset to RUNNING by {operator or 'tech'}")

    elif cmd_upper in ["STANDBY", "STOP"]:
        dev["motor_state"] = "STANDBY"
        dev["vacuum_pressure"] = 0.0
        logging.info(f"[{sn}] Motor switched to STANDBY")

    elif cmd_upper in ["START", "RUNNING"]:
        dev["motor_state"] = "RUNNING"
        dev["vacuum_pressure"] = round(random.uniform(130.0, 160.0), 2)
        logging.info(f"[{sn}] Motor started to RUNNING")

    elif cmd_upper in ["RESET_FILTER"]:
        dev["filter_status"] = "Good"
        logging.info(f"[{sn}] Filter reset to Good")


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logging.info(f"Simulator successfully connected to MQTT Broker (Code {rc})")
        for dev in DEVICES:
            control_topic = f"hospital/devices/{dev['serial_number']}/control"
            client.subscribe(control_topic, qos=1)
            logging.info(f"Subscribed to: {control_topic}")
        
        fleet_topic = "hospital/devices/fleet/control"
        client.subscribe(fleet_topic, qos=1)
        logging.info(f"Subscribed to fleet broadcast: {fleet_topic}")
    else:
        logging.error(f"Failed to connect to MQTT broker, return code {rc}")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        topic_parts = msg.topic.split("/")
        
        sn_from_topic = topic_parts[2] if len(topic_parts) >= 3 else None
        sn = payload.get("serial_number", sn_from_topic)
        cmd = payload.get("command", "")
        operator = payload.get("operator", "system")

        logging.info(f"[MQTT RECV] Topic: {msg.topic} | Target: {sn} | Command: {cmd}")

        if sn == "fleet" or msg.topic == "hospital/devices/fleet/control":
            for dev in DEVICES:
                apply_command_to_device(dev, cmd, operator)
        else:
            for dev in DEVICES:
                if dev["serial_number"] == sn:
                    apply_command_to_device(dev, cmd, operator)
    except Exception as e:
        logging.error(f"Error processing MQTT message: {e}")


def main():
    user = get_secret(MQTT_USER_FILE, os.getenv("MQTT_USER", "wms_device"))
    password = get_secret(MQTT_PASS_FILE, os.getenv("MQTT_PASSWORD", os.getenv("MQTT_PASS", "device_secure_pass")))

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
            elif dev["motor_state"] in ["STANDBY", "EMERGENCY_PARKED"]:
                dev["vacuum_pressure"] = 0.0

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
