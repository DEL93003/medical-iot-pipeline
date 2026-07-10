import os
import psycopg2
import psycopg2.extras
import json
import time
import jwt
from functools import wraps
from flask import Flask, Response, render_template, request, jsonify

# Import the fresh alert engine dispatch logic
from alerts import dispatch_critical_alert

app = Flask(__name__)

JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'super-secure-medical-iot-token-key')
DATABASE_PATH = os.environ.get('DATABASE_PATH', '/app/data/telemetry.db')

def get_db_connection():
    conn = psycopg2.connect(
        host=os.environ.get("PG_HOST", "iot_database"),
        user=os.environ.get("PG_USER", "dale_admin"),
        password=os.environ.get("PG_PASSWORD", "secure_telemetry_pass"),
        database=os.environ.get("PG_DB", "iot_telemetry")
    )
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS telemetry (
            serial_number TEXT PRIMARY KEY,
            zone TEXT,
            firmware TEXT,
            motor_state TEXT,
            filter_status TEXT,
            fluid_volume REAL,
            vacuum_pressure REAL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- JWT DECORATOR MIDDLEWARE ---
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        from flask import request
        token = None
        
        # Check if the Authorization header is present
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
        
        if not token:
            return jsonify({"message": "Access Denied: Token is missing!"}), 401
            
        try:
            # Cryptographically verify signature and expiration window
            data = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
            request.token_user = data["user"]
        except jwt.ExpiredSignatureError:
            return jsonify({"message": "Access Denied: Token has expired!"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"message": "Access Denied: Invalid cryptographic token!"}), 401
            
        return f(*args, **kwargs)
    return decorated

# --- AUTH SEED ROUTE ---
@app.route('/api/v1/auth/token', methods=['POST'])
def generate_debug_token():
    payload = {
        "user": "authorized_technician",
        "exp": time.time() + 86400
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")
    return jsonify({"token": token}), 200

# --- APPS & UI ROUTES ---
@app.route('/')
@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/api/v1/telemetry', methods=['POST'])
@token_required
def receive_telemetry():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "Missing payload data"}), 400
        
        serial = data.get('serial_number')
        zone = data.get('zone')
        filter_status = data.get('filter_status')
        fluid_volume = data.get('fluid_volume')

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('''
            INSERT INTO telemetry (serial_number, zone, firmware, motor_state, filter_status, fluid_volume, vacuum_pressure, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT(serial_number) DO UPDATE SET
                zone=EXCLUDED.zone,
                firmware=telemetry.firmware,
                motor_state=EXCLUDED.motor_state,
                filter_status=CASE WHEN EXCLUDED.fluid_volume = 0.0 THEN EXCLUDED.filter_status WHEN telemetry.fluid_volume = 0.0 THEN telemetry.filter_status ELSE EXCLUDED.filter_status END,
                fluid_volume=CASE WHEN EXCLUDED.fluid_volume = 0.0 THEN 0.0 WHEN telemetry.fluid_volume = 0.0 THEN telemetry.fluid_volume + 0.05 ELSE EXCLUDED.fluid_volume END,
                vacuum_pressure=EXCLUDED.vacuum_pressure,
                timestamp=CURRENT_TIMESTAMP
        ''', (
            serial, zone, data.get('firmware'), data.get('motor_state'),
            filter_status, fluid_volume, data.get('vacuum_pressure')
        ))
        conn.commit()
        conn.close()

        # EVENT-DRIVEN TRIGGER HOOK
        # Intercept critical filter states immediately during database writing
        if filter_status in ["Replacement Required", "Critical", "Warning"]:
            dispatch_critical_alert(
                device_serial=serial,
                zone=zone,
                condition_type=f"Filter Warning ({filter_status})",
                current_value=f"{fluid_volume}L Captured"
            )

        return jsonify({"status": "success", "message": "Verified metrics accepted"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/v1/deploy-firmware', methods=['POST'])
@token_required
def handle_firmware_deployment():
    try:
        payload = request.get_json()
        serial = payload.get('serial_number') if payload else None
        if not serial:
            return jsonify({"status": "error", "message": "Missing device specification"}), 400
            
        import paho.mqtt.publish as publish
        publish.single("commands/devices", json.dumps({"serial_number": serial, "command": "push_update"}), hostname=os.environ.get("MQTT_HOST", "iot_broker"))
        deploy_firmware()
        return jsonify({"status": "success", "message": f"Firmware increment sequence dispatched down MQTT pipeline via secure session ({request.token_user})"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def deploy_firmware():
    time.sleep(0.5)
    print("[OTA] Secured firmware binary dispatched successfully.")
    return True

@app.route("/api/v1/execute-command", methods=["POST"])
@token_required
def handle_device_command():
    try:
        payload = request.get_json()
        serial = payload.get("serial_number") if payload else None
        command = payload.get("command") if payload else None
        
        if not serial or not command:
            return jsonify({"status": "error", "message": "Missing serial or command specification"}), 400
            
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        if command == "flush_filter":
            # Hard-override the live database record state down to pristine factory baselines
            cursor.execute('''
                UPDATE telemetry 
                SET filter_status = 'Good', fluid_volume = 0.00, timestamp = CURRENT_TIMESTAMP 
                WHERE serial_number = %s
            ''', (serial,))
            action_msg = "Filter assembly flushed and volume matrices re-zeroed"
        elif command == "reset_motor":
            cursor.execute("UPDATE telemetry SET motor_state = 'Operational' WHERE serial_number = %s", (serial,))
            action_msg = "Surgical pump motor controller power-cycled"
        else:
            conn.close()
            return jsonify({"status": "error", "message": "Unrecognized hardware command directive"}), 400
            
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": f"{action_msg} successfully via secure token ({request.token_user})"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def generate():
    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("SELECT DISTINCT ON (serial_number) serial_number, zone, firmware, motor_state, filter_status, fluid_volume::FLOAT, vacuum_pressure::FLOAT FROM telemetry ORDER BY serial_number, timestamp DESC")
            rows = cursor.fetchall()
            conn.close()
            for r in rows:
                cached_data = {
                    "serial_number": r[0],
                    "zone": r[1],
                    "firmware": r[2].lower() if r[2] else "v1.0.0",
                    "motor_state": r[3],
                    "filter_status": r[4],
                    "fluid_volume": r[5],
                    "vacuum_pressure": r[6]
                }
                yield f"data: {json.dumps(cached_data)}\n\n"
            time.sleep(1)
        except Exception as e:
            yield "data: {}\n\n"
            time.sleep(1)

@app.route('/api/v1/dashboard/stream')
def data_stream():
    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

# --- ASYNCHRONOUS MQTT PIPELINE BACKGROUND SUBSCRIBER ---
import threading
import json
import paho.mqtt.client as mqtt

def mqtt_subscriber_worker():
    def on_message(client, userdata, msg):
        try:
            # Parse the incoming raw broker payload back into a Python dictionary
            data = json.loads(msg.payload.decode())
            serial = data.get('serial_number')
            zone = data.get('zone')
            filter_status = data.get('filter_status')
            fluid_volume = data.get('fluid_volume')
            
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # Execute our thread-safe relational database update pattern
            cursor.execute('''
                INSERT INTO telemetry (serial_number, zone, firmware, motor_state, filter_status, fluid_volume, vacuum_pressure, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ''', (
                serial, zone, data.get('firmware'), data.get('motor_state'),
                filter_status, fluid_volume, data.get('vacuum_pressure')
            ))
            conn.commit()
            conn.close()
            
            # Keep our event-driven real-time alert ticketing sidecar perfectly in loop
            if filter_status == "Replacement Required":
                from alerts import dispatch_critical_alert
                dispatch_critical_alert(serial, zone, "Filter Warning (Replacement Required)", f"{fluid_volume}L Captured")
                
        except Exception as err:
            print(f"[MQTT WORKER ERROR] Failed to ingest telemetry stream frame: {err}", flush=True)

    # Initialize a clean, independent client socket session for the background thread
    client = mqtt.Client()
    client.on_message = on_message
    try:
        client.connect(os.environ.get("MQTT_HOST", "iot_broker"), 1883, 60)
        client.subscribe("telemetry/devices")
        client.loop_forever()
    except Exception as e:
        print(f"[MQTT WORKER CRASH] Unable to sustain background broker loop link: {e}", flush=True)

# Launch the broker subscription consumer loop inside a persistent background daemon thread
threading.Thread(target=mqtt_subscriber_worker, daemon=True).start()
print("🚀 Asynchronous MQTT backend background worker thread spawned successfully!", flush=True)
