#!/data/data/com.termux/files/usr/bin/bash
# Backend con IA simulada: ejecuta comandos reales en Termux sin API keys
termux-wake-lock 2>/dev/null
cd "$(dirname "$0")/backend" && NEUROTOK_CUENTAS=cuentas.simulado.json python api_server.py
