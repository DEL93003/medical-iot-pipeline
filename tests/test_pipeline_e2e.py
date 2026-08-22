import json
import os
import ssl
import time
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
import psycopg2

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USER = os.getenv("MQTT_USER", "device_user")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "device_password")
CA_CERT_PATH = os.getenv("CA_CERT_PATH", "mosquitto/certs/ca.crt")

PG_HOST = os.getenv("DB_HOST", "localhost")
PG_PORT = int(os.getenv("DB_PORT", "5432"))
PG_DB = os.getenv("DB_NAME", "iot_telemetry")
PG_USER = os.getenv("DB_USER", "postgres")
PG_PASSWORD = os.getenv("DB_PASSWORD", "password")


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

    # 1. Connect via MQTT with TLS and publish
    client = mqtt.Client(
        CallbackAPIVersion.VERSION2, client_id=f"pytest_{test_serial}"
    )
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.tls_set(ca_certs=CA_CERT_PATH, tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.tls_insecure_set(True)

    client.connect(MQTT_HOST, MQTT_PORT, 10)
    topic = f"hospital/devices/{test_serial}/telemetry"
    client.publish(topic, json.dumps(test_payload))
    client.disconnect()

    # 2. Poll TimescaleDB for ingestion record (up to 10 seconds)
    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DB,
        user=PG_USER,
        password=PG_PASSWORD,
    )
    cursor = conn.cursor()

    row = None
    for _ in range(20):
        cursor.execute(
            "SELECT serial_number, zone, firmware, vacuum_pressure, fluid_volume "
            "FROM telemetry WHERE serial_number = %s;",
            (test_serial,),
        )
        row = cursor.fetchone()
        if row:
            break
        time.sleep(0.5)

    cursor.close()
    conn.close()

    # 3. Verify record assertions
    assert (
        row is not None
    ), f"Telemetry record for {test_serial} was not ingested into TimescaleDB within 10s"
    assert row[0] == test_serial
    assert row[1] == "Test-Lab-1"
    assert row[2] == "v9.9.9"
    assert row[3] == 155.5
    assert row[4] == 2.75
