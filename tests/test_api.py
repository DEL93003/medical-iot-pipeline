import pytest
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code in [200, 503]

def test_list_devices_schema():
    response = client.get("/api/v1/devices")
    if response.status_code == 200:
        data = response.json()
        assert isinstance(data, list)
        if len(data) > 0:
            item = data[0]
            assert "serial_number" in item
            assert "vacuum_pressure" in item
            assert "motor_state" in item

from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

@patch("src.api.main.mqtt.Client")
def test_reset_device_endpoint(mock_mqtt_class):
    mock_instance = MagicMock()
    mock_mqtt_class.return_value = mock_instance

    response = client.post("/api/v1/devices/WMS-OR-01/reset")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["device"] == "WMS-OR-01"
    assert data["dispatched_command"]["command"] == "RUNNING"
    assert data["dispatched_command"]["operator"] == "technician_api_reset"

@patch("src.api.main.mqtt.Client")
def test_custom_control_endpoint(mock_mqtt_class):
    mock_instance = MagicMock()
    mock_mqtt_class.return_value = mock_instance

    payload = {
        "command": "STANDBY",
        "operator": "admin_test",
        "reason": "maintenance_check"
    }
    response = client.post("/api/v1/devices/WMS-ICU-01/control", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["device"] == "WMS-ICU-01"
    assert data["dispatched_command"]["command"] == "STANDBY"
    assert data["dispatched_command"]["reason"] == "maintenance_check"
