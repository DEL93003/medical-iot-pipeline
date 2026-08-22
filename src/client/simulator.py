import json
import logging
import os
import random
import ssl
import time
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USER = os.getenv("MQTT_USER", "wms_gateway")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "gateway_secure_pass")
CA_CERT_PATH = os.getenv("CA_CERT_PATH", "mosquitto/certs/ca.crt")

DEVICES = [
    {"serial": "WMS-OR-01", "zone": "OR-1", "firmware": "v2.1.0", "motor_state": "RUNNING", "locked": False},
    {"serial": "WMS-OR-02", "zone": "OR-2", "firmware": "v2.1.0", "motor_state": "RUNNING", "locked": False},
    {"serial": "WMS-ICU-01", "zone": "ICU-North", "firmware": "v2.0.4", "motor_state": "RUNNING", "locked": False},
    {"serial": "WMS-ED-01", "zone": "ED-Trauma", "firmware": "v2.2.0", "motor_state": "RUNNING", "locked": False},
]

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logging.info("Simulator connected. Listening on control topics: hospital/devices/+/control")
        client.subscribe("hospital/devices/+/control")
    else:
        logging.error(f"Failed to connect, rc={rc}")

def on_message(client, userdata, msg):
    try:
        topic_parts = msg.topic.split("/")
        serial = topic_parts[2]
        payload = json.loads(msg.payload.decode("utf-8"))
        command = payload.get("command")
        
        for dev in DEVICES:
            if dev["serial"] == serial:
                if command == "FORCE_STANDBY":
                    dev["motor_state"] = "STANDBY"
                    dev["locked"] = True
                    reason = payload.get("reason", "Unknown reason")
                    logging.warning(f"⚡ [SAFETY LOCK ENGAGED] {serial} shifted to STANDBY. Reason: {reason}")
                elif command == "RESET":
                    dev["motor_state"] = "RUNNING"
                    dev["locked"] = False
                    logging.info(f"🔄 [SAFETY RESET] {serial} unlocked and restored to RUNNING state.")
    except Exception as e:
        logging.error(f"Error handling control message: {e}")

def run_simulator():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    
    if os.path.exists(CA_CERT_PATH):
        client.tls_set(ca_certs=CA_CERT_PATH, tls_version=ssl.PROTOCOL_TLS_CLIENT)
        client.tls_insecure_set(True)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()

    try:
        while True:
            for dev in DEVICES:
                if dev["motor_state"] == "STANDBY":
                    vac_pressure = round(random.uniform(10.0, 30.0), 1)
                else:
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
                client.publish(topic, json.dumps(payload))
                logging.info(f"Published: {dev['serial']} [{dev['motor_state']}] - {vac_pressure} kPa")
            time.sleep(3)
    except KeyboardInterrupt:
        logging.info("Stopping simulator...")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    run_simulator()
