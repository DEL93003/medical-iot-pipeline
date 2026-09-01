import json
import logging
import os
import ssl
import sys
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import paho.mqtt.client as mqtt
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

app = FastAPI(title="Medical-IoT Telemetry API", version="1.0.0")

PG_HOST = os.getenv("PG_HOST", "iot_database")
PG_DB = os.getenv("PG_DB", "iot_telemetry")
PG_USER_FILE = os.getenv("PG_USER_FILE", "/run/secrets/pg_user")
PG_PASSWORD_FILE = os.getenv("PG_PASSWORD_FILE", "/run/secrets/pg_password")

MQTT_HOST = os.getenv("MQTT_HOST", "iot_broker")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USER = os.getenv("MQTT_USER", "wms_gateway")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "gateway_secure_pass")
CA_CERT_PATH = os.getenv("CA_CERT_PATH", "/app/certs/ca.crt")


def get_secret(file_path: str, default: str = "") -> str:
    try:
        with open(file_path, "r") as f:
            return f.read().strip()
    except Exception:
        return default


def get_db_conn():
    user = get_secret(PG_USER_FILE, os.getenv("PG_USER", "dale_admin"))
    password = get_secret(PG_PASSWORD_FILE, os.getenv("PG_PASSWORD", "admin_secure_pass"))
    return psycopg2.connect(
        host=PG_HOST,
        database=PG_DB,
        user=user,
        password=password,
        connect_timeout=3
    )


def publish_mqtt_command(topic: str, payload: dict):
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="fastapi_command_gateway"
    )
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

    if os.path.exists(CA_CERT_PATH):
        client.tls_set(ca_certs=CA_CERT_PATH, tls_version=ssl.PROTOCOL_TLS_CLIENT)
        client.tls_insecure_set(True)

    client.connect(MQTT_HOST, MQTT_PORT, keepalive=10)
    client.loop_start()
    infot = client.publish(topic, json.dumps(payload), qos=1)
    infot.wait_for_publish(timeout=3)
    client.loop_stop()
    client.disconnect()


class DeviceStatus(BaseModel):
    serial_number: str
    zone: Optional[str]
    firmware: Optional[str]
    motor_state: Optional[str]
    filter_status: Optional[str]
    vacuum_pressure: Optional[float]
    fluid_volume: Optional[float]
    connectivity_status: Optional[str]
    timestamp: Optional[str]


class ControlCommandRequest(BaseModel):
    command: str
    operator: Optional[str] = "api_operator"
    reason: Optional[str] = "manual_api_dispatch"


@app.get("/")
def root():
    return {"status": "online", "service": "Medical-IoT Telemetry API"}


@app.get("/health")
@app.get("/api/v1/health")
def health_check():
    try:
        conn = get_db_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
        conn.close()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unreachable: {e}")


@app.get("/api/v1/devices", response_model=List[DeviceStatus])
def list_devices():
    try:
        conn = get_db_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT ON (serial_number)
                    serial_number,
                    zone,
                    firmware,
                    motor_state,
                    filter_status,
                    vacuum_pressure,
                    fluid_volume,
                    'ONLINE' as connectivity_status,
                    to_char(timestamp, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as timestamp
                FROM telemetry
                ORDER BY serial_number, timestamp DESC;
            """)
            rows = cur.fetchall()
        conn.close()
        return rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/devices/{serial_number}/control")
def send_device_command(serial_number: str, request: ControlCommandRequest):
    topic = f"hospital/devices/{serial_number}/control"
    payload = {
        "command": request.command.upper(),
        "operator": request.operator,
        "reason": request.reason
    }
    try:
        publish_mqtt_command(topic, payload)
        logging.info(f"Dispatched command {payload['command']} to {serial_number}")
        return {
            "status": "success",
            "device": serial_number,
            "dispatched_command": payload
        }
    except Exception as e:
        logging.error(f"Failed to publish control command: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to publish MQTT control message: {e}")


@app.post("/api/v1/devices/{serial_number}/reset")
def reset_device(serial_number: str):
    return send_device_command(
        serial_number=serial_number,
        request=ControlCommandRequest(
            command="RUNNING",
            operator="technician_api_reset",
            reason="canister_serviced_manual_reset"
        )
    )
