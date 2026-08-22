from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def receive_webhook():
    alert_data = request.json
    print(f"\n🚨 [TICKET GENERATED] {alert_data.get('condition_type')} received for device {alert_data.get('device_serial')} in {alert_data.get('zone')}!", flush=True)
    print(f"📋 Details: {alert_data.get('current_value')}\n", flush=True)
    return jsonify({"status": "ticket_created", "code": 201}), 201

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=6000)
