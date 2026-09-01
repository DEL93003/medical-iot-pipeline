import json
import logging
import os
import ssl
import sys
import time
import urllib.request
import paho.mqtt.client as mqtt
import psycopg2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

PG_HOST = os.getenv("PG_HOST", "iot_database")
PG_DB = os.getenv("PG_DB", "iot_telemetry")
PG_USER_FILE = os.getenv("PG_USER_FILE", "/run/secrets/pg_user")
PG_PASSWORD_FILE = os.getenv("PG_PASSWORD_FILE", "/run/secrets/pg_password")

MQTT_HOST = os.getenv("MQTT_HOST", "iot_broker")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USER = os.getenv("MQTT_USER", "wms_gateway")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "gateway_secure_pass")
CA_CERT_PATH = os.getenv("CA_CERT_PATH", "/app/certs/ca.crt")
TICKETING_WEBHOOK_URL = os.getenv("TICKETING_WEBHOOK_URL", "http://ticketing_service:6000/webhook")

ALERT_COOLDOWN_SECONDS = 30
recent_alerts = {}
mqtt_client_instance = None
db_conn = None


def get_secret(file_path, default=""):
    try:
        with open(file_path, "r") as f:
            return f.read().strip()
    except Exception:
        return default


def get_db_connection():
    user = get_secret(PG_USER_FILE, os.getenv("PG_USER", "dale_admin"))
    password = get_secret(PG_PASSWORD_FILE, os.getenv("PG_PASSWORD", "admin_secure_pass"))

    while True:
        try:
            conn = psycopg2.connect(
                host=PG_HOST,
                database=PG_DB,
                user=user,
                password=password,
                connect_timeout=5
            )
            logging.info("Connected to TimescaleDB successfully.")
            return conn
        except Exception as e:
            logging.error(f"Database connection error: {e}. Retrying in 3 seconds...")
            time.sleep(3)


def check_and_alert_anomalies(payload):
    serial = payload.get("serial_number", "Unknown")
    zone = payload.get("zone", "General")
    vacuum = payload.get("vacuum_pressure", 0.0)
    fluid = payload.get("fluid_volume", 0.0)
    filter_status = payload.get("filter_status", "Good")
    motor_state = payload.get("motor_state", "OFF")

    now = time.time()

    # 1. Closed-Loop Auto-Remediation: Automated STANDBY Command
    if fluid >= 3.8 and motor_state == "RUNNING":
        logging.warning(f"CRITICAL OVERFLOW RISK on {serial} ({fluid}L) -> Issuing STANDBY failsafe command")
        failsafe_payload = {
            "command": "STANDBY",
            "operator": "system_auto_remediation",
            "reason": "CRITICAL_CANISTER_OVERFLOW_FAILSAFE"
        }
        control_topic = f"hospital/devices/{serial}/control"
        if mqtt_client_instance:
            mqtt_client_instance.publish(control_topic, json.dumps(failsafe_payload), qos=1)

    # 2. Alert Cooldown Check
    if serial in recent_alerts and (now - recent_alerts[serial]) < ALERT_COOLDOWN_SECONDS:
        return

    alert_reason = None
    metric_val = None

    if fluid >= 3.5:
        alert_reason = "Canister Fluid Overflow Warning (>= 3.5L)"
        metric_val = f"{fluid} L"
    elif filter_status == "Replacement Required":
        alert_reason = "Filter Saturation - Replacement Urgently Required"
        metric_val = "100% Saturation"
    elif vacuum > 190.0:
        alert_reason = "High Vacuum Pressure Exceeded Threshold (> 190 mmHg)"
        metric_val = f"{vacuum} mmHg"

    if alert_reason:
        recent_alerts[serial] = now
        try:
            webhook_payload = json.dumps({
                "device_serial": serial,
                "zone": zone,
                "condition": alert_reason,
                "value": metric_val
            }).encode('utf-8')
            req = urllib.request.Request(
                TICKETING_WEBHOOK_URL,
                data=webhook_payload,
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=3) as res:
                if res.status in [200, 201]:
                    logging.info(f"Dispatched ticket webhook for {serial} to {TICKETING_WEBHOOK_URL}")
        except Exception as err:
            logging.error(f"Failed to post to ticketing webhook: {err}")


def on_connect(client, userdata, flags, reason_code, properties=None):
    logging.info(f"Connected to MQTT Broker (Code: {reason_code})")
    client.subscribe("hospital/devices/#", qos=0)
    logging.info("Subscribed to topic: hospital/devices/#")


def on_message(client, userdata, msg):
    global db_conn
    try:
        # Ignore control messages from database insertion
        if msg.topic.endswith("/control"):
            return

        payload = json.loads(msg.payload.decode("utf-8"))

        if db_conn is None or db_conn.closed != 0:
            db_conn = get_db_connection()

        with db_conn.cursor() as cursor:
            insert_query = """
            INSERT INTO telemetry (timestamp, serial_number, zone, firmware, motor_state, filter_status, vacuum_pressure, fluid_volume)
            VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s);
            """
            cursor.execute(insert_query, (
                payload.get("serial_number"),
                payload.get("zone", "Default"),
                payload.get("firmware", "1.0.0"),
                payload.get("motor_state", "OFF"),
                payload.get("filter_status", "Good"),
                payload.get("vacuum_pressure", 0.0),
                payload.get("fluid_volume", 0.0)
            ))
            db_conn.commit()

        logging.info(f"Ingested telemetry from {payload.get('serial_number')} [{payload.get('motor_state')}] - {payload.get('vacuum_pressure')} mmHg")
        check_and_alert_anomalies(payload)

    except Exception as e:
        logging.error(f"Error processing telemetry message: {e}")
        if db_conn and db_conn.closed == 0:
            try:
                db_conn.rollback()
            except Exception:
                pass


client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    client_id="mqtt_consumer_backend"
)
mqtt_client_instance = client
client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

if os.path.exists(CA_CERT_PATH):
    logging.info(f"Loading CA certificate from {CA_CERT_PATH}")
    client.tls_set(ca_certs=CA_CERT_PATH, tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.tls_insecure_set(True)
else:
    logging.error(f"FATAL: CA certificate not found at {CA_CERT_PATH}!")
    raise FileNotFoundError(f"Missing CA certificate at {CA_CERT_PATH}")

client.on_connect = on_connect
client.on_message = on_message

if __name__ == "__main__":
    db_conn = get_db_connection()
    connected = False
    while not connected:
        try:
            logging.info(f"Attempting connection to MQTT broker at {MQTT_HOST}:{MQTT_PORT}...")
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            connected = True
        except Exception as e:
            logging.warning(f"Broker connection failed ({e}). Retrying in 3 seconds...")
            time.sleep(3)

    client.loop_forever()
