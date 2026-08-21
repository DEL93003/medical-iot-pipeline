import requests

def dispatch_critical_alert(device_serial, zone, condition_type, current_value):
    payload = {
        "device_serial": device_serial,
        "zone": zone,
        "condition_type": condition_type,
        "current_value": current_value
    }
    url = "http://ticketing_service:6000/webhook"
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 201:
            print(f"[ALERT HOOK] Telemetry event successfully dispatched to Ticketing Module.", flush=True)
        else:
            print(f"[ALERT HOOK WARNING] Webhook dropped with status: {response.status_code}", flush=True)
    except Exception as err:
        print(f"[ALERT ENGINE ERROR] Webhook delivery failed: {err}", flush=True)
