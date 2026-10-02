#!/data/data/com.termux/files/usr/bin/bash
# Instala todo Neurotok en Termux. Uso: bash instalar.sh
set -e
cd "$(dirname "$0")"
pkg install -y python nodejs-lts unzip
pip install -r backend/requirements.txt || echo "(aviso) pip falló; el modo Demo funciona igual"
if [ ! -d app ]; then
  npx --yes create-expo-app@latest app --template blank
fi
cp app_fuente/App.js app/App.js
cp -r app_fuente/src app/
cp -r app_fuente/assets app/
echo ""
echo "Listo. Ahora ejecuta:  bash iniciar_app.sh"
