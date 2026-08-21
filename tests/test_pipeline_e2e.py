import json
import os
import ssl
import time
import pytest
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
import psycopg2

MQTT_HOST = "localhost"
MQTT_PORT = 8883
MQTT_USER = "wms_device"
MQTT_PASSWORD = "device_secure_pass"
CA_CERT_PATH = "mosquitto/certs/ca.crt"

PG_HOST = "localhost"
PG_PORT = 5432
PG_DB = "iot_telemetry"

def get_secret(filename, default=""):
    path = os.path.join(os.path.dirname(__file__), "..", ".docker_secrets", filename)
    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read().strip()
    return default

PG_USER = get_secret("pg_user.txt", "dale_admin")
PG_PASSWORD = get_secret("pg_password.txt", "password")

def test_mqtt_tls_publishing_and_db_ingestion():
    test_serial = f"TEST-UNIT-{int(time.time())}"
    test_payload = {
        "serial_number": test_serial,
        "zone": "Test-Lab-1",
        "firmware": "v9.9.9",
        "motor_state": "RUNNING",
        "filter_status": "Good",
        "vacuum_pressure": 155.5,
        "fluid_volume": 2.75
    }

    # 1. Connect via MQTT with TLS and publish
    client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=f"pytest_{test_serial}")
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.tls_set(ca_certs=CA_CERT_PATH, tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.tls_insecure_set(True)
    
    client.connect(MQTT_HOST, MQTT_PORT, 10)
    topic = f"hospital/devices/{test_serial}/telemetry"
    client.publish(topic, json.dumps(test_payload))
    client.disconnect()

    # 2. Wait for consumer ingestion
    time.sleep(2)

    # 3. Query TimescaleDB to verify persistent record
    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DB,
        user=PG_USER,
        password=PG_PASSWORD
    )
    cursor = conn.cursor()
    cursor.execute("SELECT serial_number, zone, firmware, vacuum_pressure, fluid_volume FROM telemetry WHERE serial_number = %s;", (test_serial,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    assert row is not None, "Telemetry record was not ingested into TimescaleDB"
    assert row[0] == test_serial
    assert row[1] == "Test-Lab-1"
    assert row[2] == "v9.9.9"
    assert float(row[3]) == 155.5
    assert float(row[4]) == 2.75
