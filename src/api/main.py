import os
import json
import ssl
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
import paho.mqtt.client as mqtt
from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field
from typing import List, Optional, Literal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI(
    title="Medical IoT Fleet Telemetry API",
    description="REST microservice providing fleet health, rollups, device filtering, and bidirectional control.",
    version="1.2.1"
)

# Database Configurations
PG_HOST = os.getenv("PG_HOST", "iot_database")
PG_DB = os.getenv("PG_DB", "iot_telemetry")
PG_USER_FILE = os.getenv("PG_USER_FILE", "/run/secrets/pg_user")
PG_PASSWORD_FILE = os.getenv("PG_PASSWORD_FILE", "/run/secrets/pg_password")

# MQTT Broker Configurations
MQTT_HOST = os.getenv("MQTT_HOST", os.getenv("MQTT_BROKER", "iot_broker"))
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
CA_CERT_PATH = os.getenv("CA_CERT_PATH", "/app/certs/ca.crt")
CLIENT_CERT_PATH = os.getenv("CLIENT_CERT_PATH", "/app/certs/client.crt")
CLIENT_KEY_PATH = os.getenv("CLIENT_KEY_PATH", "/app/certs/client.key")
MQTT_USER_FILE = os.getenv("MQTT_USER_FILE", "/run/secrets/mqtt_user")
MQTT_PASS_FILE = os.getenv("MQTT_PASS_FILE", "/run/secrets/mqtt_password")


def get_secret(file_path: str, default: str = "") -> str:
    try:
        with open(file_path, "r") as f:
            return f.read().strip()
    except Exception:
        return default


def get_db_connection():
    user = get_secret(PG_USER_FILE, os.getenv("PG_USER", "dale_admin"))
    password = get_secret(PG_PASSWORD_FILE, os.getenv("PG_PASSWORD", "admin_secure_pass"))
    return psycopg2.connect(
        host=PG_HOST,
        database=PG_DB,
        user=user,
        password=password,
        connect_timeout=5,
        cursor_factory=RealDictCursor
    )


def publish_mqtt_command(topic: str, payload: dict):
    user = get_secret(MQTT_USER_FILE, os.getenv("MQTT_USER", "dale_admin"))
    password = get_secret(MQTT_PASS_FILE, os.getenv("MQTT_PASSWORD", os.getenv("MQTT_PASS", "admin_secure_pass")))

    client = mqtt.Client(client_id=f"api_dispatcher_{os.getpid()}", protocol=mqtt.MQTTv311)
    if user and password:
        client.username_pw_set(username=user, password=password)

    ca = CA_CERT_PATH if os.path.exists(CA_CERT_PATH) else ("/certs/ca.crt" if os.path.exists("/certs/ca.crt") else None)
    cl_cert = CLIENT_CERT_PATH if os.path.exists(CLIENT_CERT_PATH) else ("/certs/client.crt" if os.path.exists("/certs/client.crt") else None)
    cl_key = CLIENT_KEY_PATH if os.path.exists(CLIENT_KEY_PATH) else ("/certs/client.key" if os.path.exists("/certs/client.key") else None)

    if ca:
        client.tls_set(
            ca_certs=ca,
            certfile=cl_cert if (cl_cert and os.path.exists(cl_cert)) else None,
            keyfile=cl_key if (cl_key and os.path.exists(cl_key)) else None,
            tls_version=ssl.PROTOCOL_TLSv1_2
        )
        client.tls_insecure_set(True)

    client.connect(MQTT_HOST, MQTT_PORT, keepalive=10)
    client.loop_start()

    msg_info = client.publish(topic, json.dumps(payload), qos=1)
    msg_info.wait_for_publish(timeout=5.0)

    client.loop_stop()
    client.disconnect()
    logging.info(f"Published control payload to {topic}: {payload}")


# --- Pydantic Models ---

class TelemetrySnapshot(BaseModel):
    serial_number: str
    zone: Optional[str] = None
    firmware: Optional[str] = None
    motor_state: Optional[str] = None
    filter_status: Optional[str] = None
    vacuum_pressure: Optional[float] = None
    fluid_volume: Optional[float] = None
    connectivity_status: Optional[str] = None
    timestamp: Optional[str] = None


class DeviceStats(BaseModel):
    serial_number: str
    bucket_interval: str
    avg_vacuum: Optional[float] = None
    min_vacuum: Optional[float] = None
    max_vacuum: Optional[float] = None
    avg_fluid_volume: Optional[float] = None
    max_fluid_volume: Optional[float] = None
    sample_count: int


class DeviceCommandRequest(BaseModel):
    command: Literal["START", "STOP", "PURGE_CANISTER", "RESET_FILTER"] = Field(
        ..., description="Command to dispatch to the physical unit"
    )
    operator: Optional[str] = Field("sysadmin", description="Operator identifier dispatching the command")


class DeviceCommandResponse(BaseModel):
    status: str
    serial_number: str
    command: str
    topic: str
    message: str


# --- Endpoints ---

@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    try:
        conn = get_db_connection()
        conn.close()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "degraded", "database_error": str(e)}


@app.get("/api/v1/devices", response_model=List[TelemetrySnapshot])
def list_devices(
    zone: Optional[str] = Query(None, description="Filter by hospital zone (e.g., OR-1, ED-Trauma)"),
    motor_state: Optional[str] = Query(None, description="Filter by motor state (e.g., RUNNING, IDLE, ERROR)")
):
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            query = """
                SELECT DISTINCT ON (serial_number)
                    serial_number, zone, firmware, motor_state, filter_status,
                    vacuum_pressure, fluid_volume,
                    CASE
                        WHEN timestamp >= NOW() - INTERVAL '30 seconds' THEN 'ONLINE'
                        ELSE 'OFFLINE'
                    END AS connectivity_status,
                    to_char(timestamp, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as timestamp
                FROM telemetry
                WHERE serial_number NOT LIKE 'TEST-%%'
            """
            params = []
            if zone:
                query += " AND zone = %s"
                params.append(zone)
            if motor_state:
                query += " AND motor_state = %s"
                params.append(motor_state)

            query += " ORDER BY serial_number, timestamp DESC;"
            cur.execute(query, tuple(params) if params else None)
            rows = cur.fetchall()
        conn.close()
        return rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")


@app.get("/api/v1/devices/{serial_number}", response_model=TelemetrySnapshot)
def get_device(serial_number: str):
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    serial_number, zone, firmware, motor_state, filter_status,
                    vacuum_pressure, fluid_volume,
                    CASE
                        WHEN timestamp >= NOW() - INTERVAL '30 seconds' THEN 'ONLINE'
                        ELSE 'OFFLINE'
                    END AS connectivity_status,
                    to_char(timestamp, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as timestamp
                FROM telemetry
                WHERE serial_number = %s
                ORDER BY timestamp DESC
                LIMIT 1;
            """, (serial_number,))
            row = cur.fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail=f"Device {serial_number} not found")
        return row
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")


@app.get("/api/v1/devices/{serial_number}/stats", response_model=List[DeviceStats])
def get_device_stats(
    serial_number: str,
    interval: str = Query("1 minute", description="TimescaleDB time bucket (e.g., '1 minute', '5 minutes', '1 hour')"),
    lookback_minutes: int = Query(60, description="Window of historical data in minutes")
):
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    serial_number,
                    to_char(time_bucket(%s::interval, timestamp), 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS bucket_interval,
                    ROUND(AVG(vacuum_pressure)::numeric, 2) AS avg_vacuum,
                    ROUND(MIN(vacuum_pressure)::numeric, 2) AS min_vacuum,
                    ROUND(MAX(vacuum_pressure)::numeric, 2) AS max_vacuum,
                    ROUND(AVG(fluid_volume)::numeric, 2) AS avg_fluid_volume,
                    ROUND(MAX(fluid_volume)::numeric, 2) AS max_fluid_volume,
                    COUNT(*)::int AS sample_count
                FROM telemetry
                WHERE serial_number = %s
                  AND timestamp >= NOW() - (%s * INTERVAL '1 minute')
                GROUP BY 1, time_bucket(%s::interval, timestamp)
                ORDER BY 2 DESC;
            """, (interval, serial_number, lookback_minutes, interval))
            rows = cur.fetchall()
        conn.close()
        return rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TimescaleDB analytical rollup error: {str(e)}")


@app.post("/api/v1/devices/{serial_number}/control", response_model=DeviceCommandResponse)
def send_device_command(serial_number: str, cmd_req: DeviceCommandRequest):
    topic = f"hospital/devices/{serial_number}/control"
    payload = {
        "serial_number": serial_number,
        "command": cmd_req.command,
        "operator": cmd_req.operator
    }
    try:
        publish_mqtt_command(topic, payload)
        return DeviceCommandResponse(
            status="dispatched",
            serial_number=serial_number,
            command=cmd_req.command,
            topic=topic,
            message=f"Command {cmd_req.command} successfully published to {topic}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to publish control command: {str(e)}")
