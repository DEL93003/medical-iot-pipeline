import json
from unittest.mock import MagicMock, patch
from src.server.mqtt_consumer import check_and_alert_anomalies

def test_closed_loop_standby_failsafe_trigger():
    """Verify that canister fluid >= 3.8L issues a STANDBY control message."""
    mock_mqtt = MagicMock()

    with patch("src.server.mqtt_consumer.mqtt_client_instance", mock_mqtt), \
         patch("urllib.request.urlopen") as mock_urlopen:

        # Configure mock HTTP response for webhook
        mock_response = MagicMock()
        mock_response.status = 201
        mock_urlopen.return_value.__enter__.return_value = mock_response

        critical_payload = {
            "serial_number": "WMS-TEST-01",
            "zone": "OR-1",
            "firmware": "v2.1.0",
            "motor_state": "RUNNING",
            "filter_status": "Good",
            "vacuum_pressure": 150.0,
            "fluid_volume": 3.9
        }

        check_and_alert_anomalies(critical_payload)

        # 1. Assert MQTT failsafe command was dispatched
        mock_mqtt.publish.assert_called_once()
        args, kwargs = mock_mqtt.publish.call_args
        topic = args[0]
        payload = json.loads(args[1])

        assert topic == "hospital/devices/WMS-TEST-01/control"
        assert payload["command"] == "STANDBY"
        assert payload["reason"] == "CRITICAL_CANISTER_OVERFLOW_FAILSAFE"

        # 2. Assert Incident Webhook was called
        assert mock_urlopen.called
