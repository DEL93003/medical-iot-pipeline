# 🏥 Medical IoT Telemetry Pipeline — Security & Vulnerability Assessment

This repository contains an edge-gateway architecture designed to ingest real-time surgical pump metrics via MQTT and HTTP, parse telemetry logs, and dispatch event-driven ticketing webhooks to downstream systems.

---

## 🛡️ Audited & Patched Vulnerabilities

### 1. [FIXED] Concurrency Blocking & Socket Starvation (C-Extension Lockup)
* **Vulnerability:** The gateway server mixed traditional Python `threading` with standard `psycopg2` database bindings inside an open-ended EventSource stream loop (`/api/v1/dashboard/stream`). Under heavy traffic, raw C-extensions blocked the main thread execution, resulting in dropped MQTT frames and dashboard stuttering.
* **Remediation:** Injected asynchronous runtime engines (`gevent` monkey-patching) and replaced raw single-session handles with a thread-safe connection pooling driver (`psycogreen` + `ThreadedConnectionPool`).

### 2. [FIXED] Rigid Internal Routing & Container Isolation
* **Vulnerability:** The event-driven alert dispatcher was hardcoded to hit `127.0.0.1:6000`, causing continuous `Connection refused` loop crashes inside the isolated gateway container context.
* **Remediation:** Migrated routing to an environment-driven service hostname lookup (`ticketing_service`) and linked the microservice layer explicitly inside the `wms-secure-net` virtual bridge subnet.

---

## 🚨 Active High-Priority Security Gaps (Vulnerability Checklist)

Look closely at `gateway_server.py` and your stack configuration—these are the critical items remaining to be hardened:

### 🟩 1. Broken Authentication (JWT Validation Bypass)
* **The Gap:** Inside `gateway_server.py`, the `@token_required` decorator middleware completely bypasses cryptographic checking. It contains a stub that automatically injects `request.token_user = "dale_admin"` into the thread context without reading, decoding, or verifying an incoming HTTP `Authorization: Bearer <token>` header.
* **Risk:** High. Any unauthenticated script can issue hard-override API requests to clear operational logs or alter configurations.

### 🟩 2. Hardcoded Administrative Secrets & Environment Defaults
* **The Gap:** The `JWT_SECRET_KEY` falls back to a hardcoded plaintext string (`'super-secure-medical-iot-token-key'`). Additionally, the PostgreSQL database credentials (`dale_admin`, `secure_telemetry_pass`) are exposed in cleartext defaults within `get_db_connection()` blocks.
* **Risk:** Medium-High. Attackers scraping source control configurations immediately inherit root database privileges and token-signing authorization capabilities.

### 🟩 3. Unencrypted Internal Traffic (Cleartext Network Strings)
* **The Gap:** Telemetry frames and webhook alert tickets transit across local routing lines via unencrypted HTTP and plain text MQTT (Port 1883). 
* **Risk:** Medium. Lacks mutual TLS (mTLS) enforcement. If rogue endpoints manage to link onto the broader local area network, they can intercept sensitive metrics or spoof critical telemetry alerts.

---

## 🛠️ Infrastructure Configuration Summary
* **Local Server IP:** `192.168.0.10` (Bridged Network Adapter Mode)
* **Internal Docker Subnet:** `wms-secure-net`
* **API Gateway Port:** `8080 -> 5000`
* **Ticketing Consumer Port:** `6000`

---

## 📊 Real-Time Fleet Telemetry & Visualization (Grafana)

A production-style Grafana dashboard connected to TimescaleDB (PostgreSQL) provides real-time monitoring and visual alerting across the medical IoT fleet.

### Dashboard Capabilities
* **Fluid Volume Monitoring:** Live continuous time-series streaming of fluid levels per device.
* **Vacuum Pressure Gauges:** Active horizontal bar gauges monitoring operational negative pressure thresholds (mmHg).
* **Fleet Health & Active Status:** Tabular device overview tracking serials, zones, firmware versions, and last heartbeat timestamps.
* **Filter Maintenance Alerts:** Dynamic status cards with automated visual alerting (`Good` vs. `Replacement Required`).

### Configuration & Export
* Exported dashboard schema is version-controlled under `grafana/dashboards/medical_iot_dashboard.json`.

### Automated Dashboard Provisioning (IaC)
* **Provisioning Provider:** `grafana/provisioning/dashboards/dashboards.yaml`
* Dashboards located in `grafana/dashboards/` are mounted and loaded into the `Fleet Telemetry` folder on container startup.
