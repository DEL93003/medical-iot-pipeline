import json
import logging
import os
import ssl
import sys
import time
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

ALERT_COOLDOWN_SECONDS = 60
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
    global mqtt_client_instance
    serial = payload.get("serial_number")
    vacuum = payload.get("vacuum_pressure", 0.0)
    filter_status = payload.get("filter_status", "Good")
    
    now = time.time()
    if serial in recent_alerts and (now - recent_alerts[serial]) < ALERT_COOLDOWN_SECONDS:
        return

    alert_reason = None
    if filter_status == "Replacement Required":
        alert_reason = "Filter replacement urgently required."
    elif vacuum > 190.0:
        alert_reason = f"High vacuum pressure threshold exceeded: {vacuum} kPa."

    if alert_reason and mqtt_client_instance:
        alert_payload = {
            "serial_number": serial,
            "alert": alert_reason,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        control_topic = f"hospital/devices/{serial}/control"
        mqtt_client_instance.publish(control_topic, json.dumps(alert_payload), qos=1)
        logging.warning(f"Dispatched alert to {control_topic}: {alert_reason}")
        recent_alerts[serial] = now


def on_connect(client, userdata, flags, reason_code, properties=None):
    logging.info(f"Connected to MQTT Broker (Code: {reason_code})")
    client.subscribe("hospital/devices/#", qos=0)
    logging.info("Subscribed to topic: hospital/devices/#")


def on_message(client, userdata, msg):
    global db_conn
    try:
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

        logging.info(f"Ingested telemetry from {payload.get('serial_number')} [{payload.get('motor_state')}] - {payload.get('vacuum_pressure')} kPa")
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
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_forever()
