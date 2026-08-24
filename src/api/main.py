import os
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(
    title="Medical IoT Fleet Telemetry API",
    description="REST microservice providing fleet health, live telemetry snapshots, and historical time-series queries.",
    version="1.0.0"
)

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


class TelemetrySnapshot(BaseModel):
    serial_number: str
    zone: Optional[str] = None
    firmware: Optional[str] = None
    motor_state: Optional[str] = None
    filter_status: Optional[str] = None
    vacuum_pressure: Optional[float] = None
    fluid_volume: Optional[float] = None
    timestamp: Optional[str] = None


@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    try:
        conn = get_db_connection()
        conn.close()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "degraded", "database_error": str(e)}


@app.get("/api/v1/devices", response_model=List[TelemetrySnapshot])
def list_devices():
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ON (serial_number)
                    serial_number, zone, firmware, motor_state, filter_status,
                    vacuum_pressure, fluid_volume, to_char(timestamp, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as timestamp
                FROM telemetry
                ORDER BY serial_number, timestamp DESC;
            """)
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
                    vacuum_pressure, fluid_volume, to_char(timestamp, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as timestamp
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


@app.get("/api/v1/devices/{serial_number}/history", response_model=List[TelemetrySnapshot])
def get_device_history(serial_number: str, limit: int = 50):
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    serial_number, zone, firmware, motor_state, filter_status,
                    vacuum_pressure, fluid_volume, to_char(timestamp, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as timestamp
                FROM telemetry
                WHERE serial_number = %s
                ORDER BY timestamp DESC
                LIMIT %s;
            """, (serial_number, limit))
            rows = cur.fetchall()
        conn.close()
        return rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
