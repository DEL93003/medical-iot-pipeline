import os
import pytest
import requests

BASE_URL = os.getenv("TEST_BASE_URL", "http://127.0.0.1:8080")
AUTH_URL = f"{BASE_URL}/api/v1/auth/token"
TELEMETRY_URL = f"{BASE_URL}/api/v1/telemetry"
FIRMWARE_URL = f"{BASE_URL}/api/v1/deploy-firmware"

def test_phase_1_unauthorized_intruder():
    """
    SCENARIO 1: A malicious node attempts to push fake metrics without a token.
    EXPECTED: The token_required decorator intercepts the request and blocks it with a 401.
    """
    print("\n[TEST] Launching Phase 1: Simulating unauthorized intruder payload...")
    fake_payload = {
        "serial_number": "WMS-HACKED",
        "zone": "External-Breach",
        "filter_status": "Critical",
        "fluid_volume": 99.9
    }
    response = requests.post(TELEMETRY_URL, json=fake_payload, timeout=2)
    assert response.status_code == 401
    assert "Authentication token missing" in response.json()["message"]
    print("✅ Phase 1 passed: Gateway successfully blocked the unauthorized intrusion!")

def test_phase_2_token_acquisition():
    """
    SCENARIO 2: A verified technician requests an access key from the gate.
    EXPECTED: The server responds with a 200 OK and spits out a valid JWT token.
    """
    print("\n[TEST] Launching Phase 2: Requesting cryptographic security token...")
    response = requests.post(AUTH_URL, timeout=2)
    assert response.status_code == 200
    token = response.json().get("token")
    assert token is not None
    assert len(token) > 10
    print("✅ Phase 2 passed: Secure token successfully issued to technician.")

def test_phase_3_authenticated_pipeline_flow():
    """
    SCENARIO 3: The technician uses the token to push metrics and deploy firmware.
    EXPECTED: The security decorator validates the signature, allows the write, and returns 200.
    """
    print("\n[TEST] Launching Phase 3: Executing secure authenticated workflows...")
    auth_response = requests.post(AUTH_URL, timeout=2)
    secure_token = auth_response.json()["token"]
    
    headers = {
        "Authorization": f"Bearer {secure_token}",
        "Content-Type": "application/json"
    }
    
    valid_payload = {
        "serial_number": "WMS-TEST-NODE",
        "zone": "Lab-Verification",
        "firmware": "v1.0.0",
        "motor_state": "Running",
        "filter_status": "Good",
        "fluid_volume": 1.25,
        "vacuum_pressure": 21.2
    }
    
    telemetry_response = requests.post(TELEMETRY_URL, json=valid_payload, headers=headers, timeout=2)
    assert telemetry_response.status_code == 200
    assert telemetry_response.json()["status"] == "success"
    
    firmware_payload = {"serial_number": "WMS-TEST-NODE"}
    firmware_response = requests.post(FIRMWARE_URL, json=firmware_payload, headers=headers, timeout=2)
    assert firmware_response.status_code == 200
    assert "authorized_technician" in firmware_response.json()["message"]
    print("✅ Phase 3 passed: Verified telemetry written and firmware deployment authorized!")
