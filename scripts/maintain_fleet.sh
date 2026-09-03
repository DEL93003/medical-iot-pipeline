#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="http://localhost:8000/api/v1"
OPERATOR="dale_tech"
TARGET_DEVICE="${1:-ALL}"

service_device() {
    local dev="$1"
    echo "=========================================="
    echo ">>> Servicing Device: ${dev}"
    echo "=========================================="
    
    echo "[-] Replacing filter..."
    curl -s -X POST "${API_BASE_URL}/devices/${dev}/control" \
        -H "Content-Type: application/json" \
        -d "{\"command\": \"REPLACE_FILTER\", \"operator\": \"${OPERATOR}\", \"reason\": \"scheduled_maintenance\"}" | jq -r '"    Filter replaced: " + .status'

    echo "[-] Purging canister & resetting motor..."
    curl -s -X POST "${API_BASE_URL}/devices/${dev}/control" \
        -H "Content-Type: application/json" \
        -d "{\"command\": \"PURGE_CANISTER\", \"operator\": \"${OPERATOR}\", \"reason\": \"canister_drain_cycle\"}" | jq -r '"    Purge status: " + .status'
    echo ""
}

if [[ "${TARGET_DEVICE}" == "ALL" ]]; then
    echo "Fetching all active devices from fleet API..."
    DEVICES=$(curl -s "${API_BASE_URL}/devices" | jq -r '.[].serial_number')
    for d in ${DEVICES}; do
        service_device "${d}"
    done
else
    service_device "${TARGET_DEVICE}"
fi

echo "Waiting 3 seconds for telemetry cycle..."
sleep 3

echo "=========================================="
echo ">>> Current Fleet Health"
echo "=========================================="
curl -s "${API_BASE_URL}/devices" | jq -r '.[] | "\(.serial_number) | Zone: \(.zone) | Motor: \(.motor_state) | Filter: \(.filter_status) | Fluid: \(.fluid_volume)L | Vacuum: \(.vacuum_pressure) mmHg"'
