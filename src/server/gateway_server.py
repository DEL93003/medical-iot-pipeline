import logging
import os
import psycopg2
from flask import Flask, jsonify, request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

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


def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise e


def dispatch_critical_alert(serial, zone, alert_type, detail):
    logger.warning(f"ALERT DISPATCHED: [{serial}] ({zone}) - {alert_type}: {detail}")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"}), 200


@app.route("/telemetry", methods=["POST"])
def receive_telemetry():
    data = request.get_json() or {}
    serial = data.get("serial_number")
    zone = data.get("zone")
    fluid_volume = float(data.get("fluid_volume", 0.0))

    filter_status = (
        "Replacement Required"
        if fluid_volume >= 0.8
        else ("Warning" if fluid_volume >= 0.5 else data.get("filter_status", "Good"))
    )

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO telemetry (serial_number, zone, firmware, motor_state, filter_status, fluid_volume, vacuum_pressure, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            """,
            (
                serial,
                zone,
                data.get("firmware"),
                data.get("motor_state"),
                filter_status,
                fluid_volume,
                data.get("vacuum_pressure"),
            ),
        )
        conn.commit()
        cur.close()
        conn.close()

        if filter_status in ["Replacement Required", "Warning"]:
            dispatch_critical_alert(
                serial, zone, f"Filter Warning ({filter_status})", f"{fluid_volume}L Captured"
            )
        return jsonify({"message": "Verified metrics accepted", "status": "success"}), 200
    except Exception as e:
        return jsonify({"message": str(e), "status": "error"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
