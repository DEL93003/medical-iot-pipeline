from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from src.api.main import app

client = TestClient(app)


def test_health_check(monkeypatch):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    monkeypatch.setattr("src.api.main.get_db_conn", lambda: mock_conn)

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_list_devices(monkeypatch):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [
        {
            "serial_number": "WMS-ED-01",
            "zone": "ED-Trauma",
            "firmware": "v2.2.0",
            "motor_state": "RUNNING",
            "filter_status": "Good",
            "vacuum_pressure": 135.0,
            "fluid_volume": 0.5,
            "connectivity_status": "ONLINE",
            "timestamp": "2026-09-01T04:40:00Z"
        }
    ]
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    monkeypatch.setattr("src.api.main.get_db_conn", lambda: mock_conn)

    response = client.get("/api/v1/devices")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["serial_number"] == "WMS-ED-01"
    assert data[0]["motor_state"] == "RUNNING"


@patch("src.api.main.publish_mqtt_command")
def test_send_purge_command(mock_publish):
    payload = {
        "command": "PURGE_CANISTER",
        "operator": "test_runner",
        "reason": "automated_unit_test"
    }
    response = client.post("/api/v1/devices/WMS-ED-01/control", json=payload)

    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    assert res_data["device"] == "WMS-ED-01"
    assert res_data["dispatched_command"]["command"] == "PURGE_CANISTER"

    mock_publish.assert_called_once_with(
        "hospital/devices/WMS-ED-01/control",
        {
            "command": "PURGE_CANISTER",
            "operator": "test_runner",
            "reason": "automated_unit_test"
        }
    )


@patch("src.api.main.publish_mqtt_command")
def test_reset_endpoint(mock_publish):
    response = client.post("/api/v1/devices/WMS-OR-01/reset")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    assert res_data["device"] == "WMS-OR-01"
    assert res_data["dispatched_command"]["command"] == "PURGE_CANISTER"

    mock_publish.assert_called_once_with(
        "hospital/devices/WMS-OR-01/control",
        {
            "command": "PURGE_CANISTER",
            "operator": "technician_api_reset",
            "reason": "canister_serviced_manual_reset"
        }
    )


def test_control_invalid_payload():
    response = client.post("/api/v1/devices/WMS-ED-01/control", json={})
    assert response.status_code == 422
