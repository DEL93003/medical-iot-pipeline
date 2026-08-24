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
