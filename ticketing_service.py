import json
import logging
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

TICKET_FILE = "incident_tickets.log"
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class TicketingHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/webhook':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)

            try:
                data = json.loads(body.decode('utf-8'))
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "rejected", "reason": "Invalid JSON"}).encode('utf-8'))
                return

            # Grafana Alertmanager payload
            if "alerts" in data and isinstance(data["alerts"], list) and len(data["alerts"]) > 0:
                first_alert = data["alerts"][0]
                labels = first_alert.get("labels", {})
                annotations = first_alert.get("annotations", {})
                values = first_alert.get("values", {})


                device = labels.get("serial_number") or labels.get("device_serial") or labels.get("metric") or "Unknown"
                zone = labels.get("zone", "Hospital Floor")
                condition = annotations.get("summary") or labels.get("alertname", "Unknown Fault")
                value = list(values.values())[0] if values else "N/A"
            else:
                # Direct pipeline payload
                device = data.get("device_serial", "Unknown")
                zone = data.get("zone", "Unknown")
                condition = data.get("condition") or data.get("condition_type", "Unknown")
                value = data.get("value") or data.get("current_value", "N/A")

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            ticket_entry = f"""
================================================================================
[INCIDENT TICKET GENERATED - {timestamp}]
--------------------------------------------------------------------------------
Device Asset Tag : {device}
Facility Zone    : {zone}
Trigger Fault    : {condition}
Recorded Metric  : {value}
Status           : ASSIGNED TO FIELD TECHNICIAN
================================================================================
"""
            with open(TICKET_FILE, "a") as f:
                f.write(ticket_entry)

            logging.info(f"Successfully created incident ticket for {device} ({zone}) - Fault: {condition}")

            self.send_response(201)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ticket_created", "asset": device}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    server_address = ('0.0.0.0', 6000)
    httpd = HTTPServer(server_address, TicketingHandler)
    logging.info("Downstream Ticketing Microservice Booted. Listening on port 6000...")
    httpd.serve_forever()
