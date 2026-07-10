import os
from flask import Flask, render_template
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# The secure internal private IP route used by Cloud Run via the VPC connector
# Change this line to use the public IP for local testing:
DB_URL = "postgresql://postgres:SororitasTelemetry2026%21@35.192.157.114:5432/postgres"

def get_fleet_data():
    conn = psycopg2.connect(DB_URL)
    # Using RealDictCursor lets us handle column names cleanly in HTML templates
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # 1. Fetch the latest status for the active fleet nodes
    cur.execute("""
        SELECT DISTINCT ON (serial_number) 
            serial_number, zone, firmware, motor_state, filter_status, fluid_volume, vacuum_pressure, timestamp
        FROM telemetry 
        ORDER BY serial_number, timestamp DESC;
    """)
    nodes = cur.fetchall()
    
    # 2. Fetch any un-resolved incidents logged by our new database trigger
    cur.execute("""
        SELECT alert_id, serial_number, zone, issue_type, recorded_value, timestamp 
        FROM system_alerts 
        WHERE resolved = FALSE 
        ORDER BY timestamp DESC;
    """)
    alerts = cur.fetchall()
    
    cur.close()
    conn.close()
    return nodes, alerts

@app.route("/")
def index():
    try:
        fleet_nodes, critical_alerts = get_fleet_data()
        return render_template("index.html", nodes=fleet_nodes, alerts=critical_alerts)
    except Exception as e:
        return f"Dashboard Connection Error: {e}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
