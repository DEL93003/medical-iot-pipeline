import os
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)
TICKET_FILE = "incident_tickets.txt"

@app.route('/webhook', methods=['POST'])
def receive_alert_webhook():
    data = request.get_json()
    if not data:
        return jsonify({"status": "rejected", "reason": "No payload data"}), 400

    device = data.get("device_serial", "Unknown")
    zone = data.get("zone", "Unknown")
    condition = data.get("condition", "Unknown")
    value = data.get("value", "N/A")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Format a clean, professional enterprise IT support incident ticket
    ticket_entry = f"""
[INCIDENT TICKET GENERATED - {timestamp}]
--------------------------------------------------
Device Asset Tag : {device}
Facility Zone    : {zone}
Trigger Fault    : {condition}
Recorded Metric  : {value}
Status           : ASSIGNED TO FIELD TECHNICIAN
--------------------------------------------------
\n"""

    # Persist the ticket to our local incident logging ledger file
    with open(TICKET_FILE, "a") as f:
        f.write(ticket_entry)

    print(f"⚠️ [TICKETING SERVICE] Successfully processed asset ticket for {device} in {zone}.")
    return jsonify({"status": "ticket_created", "asset": device}), 201

if __name__ == "__main__":
    print("🚀 Downstream Ticketing Microservice Booted. Listening on port 6000...", flush=True)
    app.run(host="0.0.0.0", port=6000)
