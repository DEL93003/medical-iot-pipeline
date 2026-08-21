import json
import logging
import os
import ssl
import time
import paho.mqtt.client as mqtt
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

PG_HOST = os.getenv("PG_HOST", "iot_database")
PG_DB = os.getenv("PG_DB", "iot_telemetry")
PG_USER_FILE = os.getenv("PG_USER_FILE", "/run/secrets/pg_user")
PG_PASSWORD_FILE = os.getenv("PG_PASSWORD_FILE", "/run/secrets/pg_password")

MQTT_HOST = os.getenv("MQTT_HOST", "iot_broker")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USER = os.getenv("MQTT_USER", "wms_gateway")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "gateway_secure_pass")
CA_CERT_PATH = os.getenv("CA_CERT_PATH", "/app/certs/ca.crt")

def get_secret(file_path, default=""):
    try:
        with open(file_path, "r") as f:
            return f.read().strip()
    except Exception:
        return default

def get_db_connection():
    user = get_secret(PG_USER_FILE, "dale_admin")
    password = get_secret(PG_PASSWORD_FILE, "password")
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
            logging.error(f"Database connection error: {e}. Retrying in 5s...")
            time.sleep(5)

db_conn = get_db_connection()

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logging.info("Connected securely to MQTT Broker.")
        client.subscribe("hospital/devices/#")
    else:
        logging.error(f"Failed to connect to MQTT broker, return code {rc}")

def on_message(client, userdata, msg):
    global db_conn
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        cursor = db_conn.cursor()
        
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
        cursor.close()
        logging.info(f"Ingested telemetry from {payload.get('serial_number')}")
    except Exception as e:
        logging.error(f"Error processing telemetry: {e}")
        if db_conn.closed:
            db_conn = get_db_connection()

client = mqtt.Client()
client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

if os.path.exists(CA_CERT_PATH):
    client.tls_set(ca_certs=CA_CERT_PATH, tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.tls_insecure_set(True)

client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_HOST, MQTT_PORT, 60)
client.loop_forever()
