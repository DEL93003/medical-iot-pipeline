# Medical-IOT Telemetry & Auto-Remediation Pipeline

A secure, containerized, and automated telemetry pipeline designed for clinical suction and fluid waste management systems (WMS). Built to handle real-time edge telemetry, TLS-encrypted MQTT messaging, TimescaleDB metric ingestion, automated IT incident ticketing, closed-loop safety remediation, and interactive Grafana observability.

---

## Architecture Overview

<!-- Architecture Diagram -->
* Edge Simulator -> Eclipse Mosquitto (TLS 8883) -> MQTTconsumer + FastAPI
* Metrics -> TimescaleDB, Alerts -> Ticketing Webhook, Dashboards -> Grafana

---

## Features

- **TLS-Encrypted MQTT Broker**: Eclipse Mosquitto with TLS 8883, ACL policies (`wms_device`, `wms_gateway`).
- **High-Performance Time-Series Storage**: PostgreSQL 16 with TimescaleDB hypertables.
- **Closed-Loop Safety Failsafe**: Automatic MQTT `STANDBY` commands when fluid >= 3.8L.
- **Automated Incident Ticketing**: Webhook dispatching tickets to `incident_tickets.txt` for fluid, filter, and vacuum anomalies.
- **RESTful Device Control API**: FastAPI endpoints for real-time status, diagnostics, and manual resets.
- **Full CI/CD Quality Gate**: GitHub Actions pipeline with Flake8 and pytest E2E tests.

---

## Microservices Breakdown

| Service Name | Port | Description |
| :--- | :--- | :--- |
| `iot_broker` | 1883, 8883 | Eclipse Mosquitto broker (TLS & plaintext) |
| `iot_database` | 5432 | TimescaleDB / PostgreSQL database |
| `mqtt_consumer` | -- | Ingestion worker, anomaly detector, and failsafe engine |
| `wms_fleet_simulator` | -- | Multi-device clinical telemetry simulator |
| `telemetry_api` | 8000 | FastAPI REST microservice |
| `ticketing_service` | 6000 | Incident webhook receiver logger |
| `iot_grafana` | 3000 | Live observability dashboard |

---

## Quick Start & Run Commands

### 1. Start the Application Stack
```bash
docker compose up -d --build
psycopg2
```

### 2. Run Tests & Linting
```bash
docker compose exec telemetry_api pytest tests/ -v
docker compose exec telemetry_api flake8 src tests
```

---

## REST API Endpoints

**Base URL**: `http://localhost:8000`

*`GET /api/v1/health`: System & database health check
*`GET /api/v1/devices`: Fetch latest fleet status
*`POST /api/v1/devices/{serial_number}/reset`: Manual operator device reset
*`POST /api/v1/devicer/{serial_number}/control`: Dispatch arbitrary MATT control commands
