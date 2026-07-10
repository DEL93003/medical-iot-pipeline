#!/bin/bash
echo "================================================================="
echo "🚀 RESETTING SYNCHRONIZED INDUSTRIAL IoT STACK"
echo "================================================================="

# 1. Purge legacy container instances completely
docker rm -f gateway_server wms_fleet_simulator 2>/dev/null

# 2. Extract the current explicit directory path
REAL_PATH="$(pwd)"
echo "📂 Synchronizing database to path: $REAL_PATH/data"

# 3. Create a real local data directory on your host disk
mkdir -p "$REAL_PATH/data"
chmod 777 "$REAL_PATH/data"

# 4. Spawn the Gateway Server mounted to the explicit local path folder
echo "🧠 Deploying Gateway Server Backend..."
docker run -d \
  --name gateway_server \
  --network wms-secure-net \
  --network-alias wms_gateway_server \
  -p 5000:5000 \
  -v "$REAL_PATH/data:/app/data" \
  -v "$REAL_PATH/src/server/templates:/app/templates" \
  -e DATABASE_PATH=/app/data/telemetry.db \
  -e FLASK_ENV=production \
  medical-iot-pipeline-gateway_server

# 5. Let the schema build script finish its initialize step
sleep 2

# 6. Spawn the Simulator Client mapped to the exact same shared local directory path
echo "📡 Deploying Synchronized Data Simulator..."
docker run -d \
  --name wms_fleet_simulator \
  --network wms-secure-net \
  -v "$REAL_PATH/data:/app/data" \
  -e TEST_BASE_URL="http://wms_gateway_server:5000" \
  -e DATABASE_PATH=/app/data/telemetry.db \
  medical-iot-pipeline-fleet_simulator

echo "================================================================="
echo "🟩 ARCHITECTURE LOCKED IN: Refresh http://127.0.0.1:5000"
echo "================================================================="
