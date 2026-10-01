#!/data/data/com.termux/files/usr/bin/bash
# Arranca la app (Expo). En Expo Go: Enter URL manually -> exp://127.0.0.1:8081
cd "$(dirname "$0")/app" && npx expo start
