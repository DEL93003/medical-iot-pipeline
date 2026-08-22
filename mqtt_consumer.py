import json
import os
import sys
import time
import psycopg2
import paho.mqtt.client as mqtt

sys.stdout.reconfigure(line_buffering=True)

# Database credentials
DB_HOST = os.getenv("DB_HOST", "iot_database")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "iot_telemetry")

DB_USER_FILE = os.getenv("DB_USER_FILE", "/run/secrets/pg_user")
DB_PASS_FILE = os.getenv("DB_PASS_FILE", "/run/secrets/pg_password")

if os.path.exists(DB_USER_FILE):
    with open(DB_USER_FILE, "r") as f:
        DB_USER = f.read().strip()
else:
    DB_USER = os.getenv("DB_USER", "postgres")

if os.path.exists(DB_PASS_FILE):
    with open(DB_PASS_FILE, "r") as f:
        DB_PASS = f.read().strip()
else:
    DB_PASS = os.getenv("DB_PASS", "postgres")

# MQTT credentials
MQTT_BROKER = os.getenv("MQTT_BROKER", "iot_broker")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "telemetry/devices")
MQTT_USER = os.getenv("MQTT_USER", "wms_gateway")
MQTT_PASS = os.getenv("MQTT_PASSWORD", "gateway_secure_pass")


def get_db_connection():
    while True:
        try:
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASS
            )
            return conn
        except psycopg2.OperationalError as e:
            print(f"Waiting for database connection... ({e})", flush=True)
            time.sleep(2)


def on_connect(client, userdata, flags, rc, properties=None):
    print(f"Connected to MQTT broker with result code: {rc}", flush=True)
    client.subscribe(MQTT_TOPIC)
    print(f"Subscribed successfully to topic: {MQTT_TOPIC}", flush=True)


def on_message(client, userdata, msg):
    try:
        payload_raw = msg.payload.decode("utf-8")
        data = json.loads(payload_raw)
        serial = data.get("serial_number")
        zone = data.get("zone")
        firmware = data.get("firmware")
        motor_state = data.get("motor_state")
        fluid_volume = float(data.get("fluid_volume", 0.0))
        vacuum_pressure = float(data.get("vacuum_pressure", 0.0))
        filter_status = (
            "Replacement Required"
            if fluid_volume >= 0.8
            else data.get("filter_status", "Good")
        )

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO telemetry (serial_number, zone, firmware, motor_state, filter_status, fluid_volume, vacuum_pressure, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP);
            """,
            (serial, zone, firmware, motor_state, filter_status, fluid_volume, vacuum_pressure)
        )
        conn.commit()
        cur.close()
        conn.close()

        print(f"Persisted record for {serial} | Vol: {fluid_volume}L | Vac: {vacuum_pressure}kPa", flush=True)

    except Exception as e:
        print(f"Error processing packet: {e}", flush=True)


def main():
    print("Starting authenticated MQTT Consumer daemon...", flush=True)
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        client = mqtt.Client()

    if MQTT_USER and MQTT_PASS:
        client.username_pw_set(MQTT_USER, MQTT_PASS)

    client.on_connect = on_connect
    client.on_message = on_message

    connected = False
    while not connected:
        try:
            print(f"Connecting to broker at {MQTT_BROKER}:{MQTT_PORT}...", flush=True)
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            connected = True
        except Exception as e:
            print(f"Broker connection failed: {e}. Retrying in 2 seconds...", flush=True)
            time.sleep(2)

    client.loop_forever()


if __name__ == "__main__":
    main()
