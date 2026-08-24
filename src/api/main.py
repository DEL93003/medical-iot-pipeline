import os
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(
    title="Medical IoT Fleet Telemetry API",
    description="REST microservice providing fleet health, rollups, device filtering, and historical queries.",
    version="1.1.1"
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
