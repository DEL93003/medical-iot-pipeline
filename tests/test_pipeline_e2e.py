import os
import ssl
import time
import json
import pytest
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
import psycopg2
from psycopg2.extras import RealDictCursor

MQTT_HOST = os.getenv("MQTT_HOST", "iot_broker")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USER = os.getenv("MQTT_USER", "wms_device")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "device_secure_pass")
CA_CERT_PATH = os.getenv("CA_CERT_PATH", "/app/certs/ca.crt")

PG_HOST = os.getenv("PG_HOST", "iot_database")
PG_DB = os.getenv("PG_DB", "iot_telemetry")
PG_USER_FILE = os.getenv("PG_USER_FILE", "/run/secrets/pg_user")
PG_PASSWORD_FILE = os.getenv("PG_PASSWORD_FILE", "/run/secrets/pg_password")


def get_secret(file_path: str, default: str = "") -> str:
    try:
        with open(file_path, "r") as f:
            return f.read().strip()
    except Exception:
        return default


def test_mqtt_tls_publishing_and_db_ingestion():
    test_serial = f"TEST-UNIT-{int(time.time())}"
    test_payload = {
        "serial_number": test_serial,
        "zone": "Test-Lab-1",
        "firmware": "v9.9.9",
        "motor_state": "RUNNING",
        "filter_status": "Good",
        "vacuum_pressure": 155.5,
        "fluid_volume": 2.75,
    }

    client = mqtt.Client(
        CallbackAPIVersion.VERSION2, client_id=f"pytest_{test_serial}"
    )
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

    ca_path = CA_CERT_PATH if os.path.exists(CA_CERT_PATH) else "certs/ca.crt"
    client.tls_set(ca_certs=ca_path, tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.tls_insecure_set(True)

    client.connect(MQTT_HOST, MQTT_PORT, 10)
    client.loop_start()

    topic = f"hospital/devices/{test_payload['serial_number']}/telemetry"
    client.publish(topic, json.dumps(test_payload), qos=1)
    time.sleep(2)
    client.loop_stop()
    client.disconnect()

    user = get_secret(PG_USER_FILE, os.getenv("PG_USER", "dale_admin"))
    password = get_secret(PG_PASSWORD_FILE, os.getenv("PG_PASSWORD", "admin_secure_pass"))

    conn = psycopg2.connect(
        host=PG_HOST,
        database=PG_DB,
        user=user,
        password=password,
        connect_timeout=5,
        cursor_factory=RealDictCursor
    )
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM telemetry WHERE serial_number = %s ORDER BY timestamp DESC LIMIT 1;",
            (test_serial,)
        )
        record = cur.fetchone()
    conn.close()

    assert record is not None
    assert record["serial_number"] == test_serial
    assert float(record["vacuum_pressure"]) == 155.5
    assert float(record["fluid_volume"]) == 2.75
