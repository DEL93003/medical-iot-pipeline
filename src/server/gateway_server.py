import os
import signal
import sys
import sqlite3
from flask import Flask, render_template, Response, request, jsonify
import time
import json
import queue

app = Flask(__name__)
stream_queue = queue.Queue()

# 1. Cloud Configuration Extraction
# We pull configuration directly from the host environment, defaulting to local files if blank
DB_PATH = os.getenv("DATABASE_PATH", "/app/database/telemetry.db")
DATABASE_URL = os.getenv("DATABASE_URL", None) # Reserved for Cloud PostgreSQL connection string

def get_db_connection():
    """Handles thread-safe local storage connections, prepped for managed cloud engines."""
    if DATABASE_URL:
        # This handle is ready to accept cloud-managed database drivers (e.g., psycopg2)
        # For our local readiness state, we continue using our optimized WAL SQLite engine
        pass
        
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10.0)
    conn.execute('PRAGMA journal_mode=WAL;')
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS telemetry (
            serial_number TEXT PRIMARY KEY,
            zone TEXT,
            firmware TEXT,
            motor_state TEXT,
            filter_status TEXT,
            fluid_volume REAL,
            vacuum_pressure REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    cursor.execute("INSERT OR IGNORE INTO system_config (key, value) VALUES ('target_firmware', 'v1.0.0')")
    conn.commit()
    conn.close()

init_db()

def get_target_version():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM system_config WHERE key='target_firmware'")
        row = cursor.fetchone()
        conn.close()
        return row[0].lower() if row else "v1.0.0"
    except Exception:
        return "v1.0.0"

def set_target_version(version):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('target_firmware', ?)", (version.lower(),))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Cloud Config Write Sync Failure: {e}", file=sys.stderr)

def save_telemetry(data):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO telemetry (serial_number, zone, firmware, motor_state, filter_status, fluid_volume, vacuum_pressure, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(serial_number) DO UPDATE SET
                zone=excluded.zone,
                firmware=excluded.firmware,
                motor_state=excluded.motor_state,
                filter_status=excluded.filter_status,
                fluid_volume=excluded.fluid_volume,
                vacuum_pressure=excluded.vacuum_pressure,
                timestamp=CURRENT_TIMESTAMP
        ''', (
            data['serial_number'], data['zone'], data.get('firmware', 'v1.0.0').lower(),
            data['motor_state'], data['filter_status'], data['fluid_volume'], data['vacuum_pressure']
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database write failure: {e}", file=sys.stderr)

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/api/v1/telemetry', methods=['POST'])
def receive_telemetry():
    data = request.json
    if data:
        save_telemetry(data)
        stream_queue.put(data)
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "invalid_data"}), 400

@app.route('/api/v1/firmware/deploy', methods=['POST'])
def deploy_firmware():
    payload = request.json
    if payload and "version" in payload:
        version = payload["version"]
        set_target_version(version)
        
        while not stream_queue.empty():
            try:
                stream_queue.get_nowait()
            except queue.Empty:
                break
                
        return jsonify({"status": "broadcast_initiated", "target": version}), 200
    return jsonify({"status": "error"}), 400

@app.route('/api/v1/firmware/check', methods=['GET'])
def check_firmware():
    return jsonify({"target_version": get_target_version()}), 200

@app.route('/api/v1/dashboard/stream')
def data_stream():
    def generate():
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT serial_number, zone, firmware, motor_state, filter_status, fluid_volume, vacuum_pressure FROM telemetry")
            rows = cursor.fetchall()
            conn.close()
            for r in rows:
                cached_data = {
                    "serial_number": r[0], "zone": r[1], "firmware": r[2].lower(),
                    "motor_state": r[3], "filter_status": r[4], "fluid_volume": r[5], "vacuum_pressure": r[6]
                }
                yield f"data: {json.dumps(cached_data)}\n\n"
        except Exception:
            pass

        while True:
            try:
                data = stream_queue.get(timeout=1.0)
                yield f"data: {json.dumps(data)}\n\n"
            except queue.Empty:
                yield ": keep-alive\n\n"
    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
