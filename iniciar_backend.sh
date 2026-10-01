#!/data/data/com.termux/files/usr/bin/bash
# Arranca el servidor API en http://127.0.0.1:8000 (necesita keys en backend/cuentas.json)
termux-wake-lock 2>/dev/null
cd "$(dirname "$0")/backend" && python api_server.py
