#!/usr/bin/env python3
"""fase_apk.py - Tarea 1: APK de Neurotok por GitHub Actions. Ejecutar desde ~/neurotok. Idempotente.
Escribe .github/workflows/{ci,apk}.yml y app_fuente/plugins/withLocalhostCleartext.js, y ajusta
app_fuente/app.json (nombre, icono, splash, paquete, plugin de red). No toca src/, App.js ni el backend.
Si falta algo (package.json, app.json, assets), no escribe nada y avisa."""
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

R = pathlib.Path(".")
APP = R / "app_fuente"
FONDO = "#0b0b0d"  # negro mate del tema (solo fondo de icono/splash)

PLUGIN = r'''// Plugin de configuración de Expo: permite HTTP SOLO a 127.0.0.1 y localhost.
// La app habla con el backend que corre en el propio teléfono (http://127.0.0.1:8000) y Android
// release bloquea HTTP por defecto. Cualquier otro dominio sigue exigiendo HTTPS.
const fs = require('fs');
const path = require('path');
const { withAndroidManifest, withDangerousMod } = require('expo/config-plugins');

const XML = `<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
  <base-config cleartextTrafficPermitted="false" />
  <domain-config cleartextTrafficPermitted="true">
    <domain includeSubdomains="false">127.0.0.1</domain>
    <domain includeSubdomains="false">localhost</domain>
  </domain-config>
</network-security-config>
`;

module.exports = function withLocalhostCleartext(config) {
  // 1) el archivo res/xml/network_security_config.xml (se escribe tras copiar la plantilla nativa)
  config = withDangerousMod(config, [
    'android',
    async (cfg) => {
      const dir = path.join(cfg.modRequest.platformProjectRoot, 'app', 'src', 'main', 'res', 'xml');
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(path.join(dir, 'network_security_config.xml'), XML);
      return cfg;
    },
  ]);
  // 2) referenciarlo desde el AndroidManifest; el tráfico en claro global queda explícitamente apagado
  return withAndroidManifest(config, (cfg) => {
    const app = cfg.modResults.manifest.application[0];
    app.$['android:networkSecurityConfig'] = '@xml/network_security_config';
    app.$['android:usesCleartextTraffic'] = 'false';
    return cfg;
  });
};
'''
CI = r'''name: CI

on:
  push:
  pull_request:
    branches: [main]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  backend:
    name: Backend (Python)
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Compilar todo el backend
        run: python -m py_compile backend/*.py
      - name: Autoprueba de la boveda
        run: python backend/boveda_db.py
      - name: Autoprueba del filtro de entrada
        run: |
          if [ -f backend/prompt_filter.py ]; then python backend/prompt_filter.py > /dev/null; fi

  app-sintaxis:
    name: App (sintaxis JS/JSX)
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
      - name: Comprobar la sintaxis de todos los archivos JS de la app
        working-directory: app_fuente
        run: |
          mapfile -t ARCHIVOS < <(find . \( -name node_modules -o -name android -o -name ios -o -name .expo \) -prune -o -type f \( -name '*.js' -o -name '*.jsx' \) -print)
          echo "Archivos a comprobar: ${#ARCHIVOS[@]}"
          [ "${#ARCHIVOS[@]}" -gt 0 ] || { echo "No hay archivos JS en app_fuente"; exit 1; }
          npx --yes esbuild@0.25.0 "${ARCHIVOS[@]}" --loader:.js=jsx --log-level=warning --outdir=/tmp/syntax

  app-bundle:
    # Compila de verdad (Metro + Hermes). No bloquea mientras no se haya visto verde; cuando lo
    # sea, quita la linea "continue-on-error".
    name: App (empaquetado Expo, no bloquea)
    runs-on: ubuntu-latest
    timeout-minutes: 20
    continue-on-error: true
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
      - uses: actions/cache@v4
        with:
          path: ~/.npm
          key: npm-${{ runner.os }}-${{ hashFiles('app_fuente/package.json', 'app_fuente/package-lock.json') }}
          restore-keys: npm-${{ runner.os }}-
      - name: Instalar dependencias
        working-directory: app_fuente
        run: npm ci --no-audit --no-fund || npm install --no-audit --no-fund
      - name: Empaquetar para Android
        working-directory: app_fuente
        env:
          CI: "1"
          EXPO_NO_TELEMETRY: "1"
        run: npx expo export --platform android --output-dir /tmp/export
'''
APK = r'''name: APK

# Como lanzarlo: GitHub > Actions > APK > Run workflow (elige la rama).
# Tambien se lanza solo al subir cambios a la rama feat/apk o una etiqueta v*.
on:
  workflow_dispatch:
  push:
    branches: [feat/apk]
    paths:
      - ".github/workflows/apk.yml"
      - "app_fuente/**"
    tags: ["v*"]

concurrency:
  group: apk-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  apk:
    name: Compilar APK
    runs-on: ubuntu-latest
    timeout-minutes: 60
    env:
      CI: "1"
      EXPO_NO_TELEMETRY: "1"
    defaults:
      run:
        working-directory: app_fuente
    steps:
      - uses: actions/checkout@v4

      # Node 22 y JDK 17 valen para Expo SDK 54 y 55 (Gradle 8.14 / 9, que piden JDK 17 o mas).
      - uses: actions/setup-node@v4
        with:
          node-version: 22
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: 17

      - uses: actions/cache@v4
        with:
          path: ~/.npm
          key: npm-${{ runner.os }}-${{ hashFiles('app_fuente/package.json', 'app_fuente/package-lock.json') }}
          restore-keys: npm-${{ runner.os }}-

      - name: Instalar dependencias
        run: npm ci --no-audit --no-fund || npm install --no-audit --no-fund

      - name: Comprobar versiones y dependencias nativas
        run: |
          node -e "
          const p = require('./package.json');
          const d = { ...p.dependencies, ...p.devDependencies };
          for (const k of ['expo', 'react-native', 'react-native-svg', '@react-native-async-storage/async-storage']) {
            if (!d[k]) { console.error('Falta en package.json: ' + k); process.exit(1); }
            console.log(k + ' ' + d[k]);
          }"
          node --version
          java -version

      - name: Generar el proyecto Android (expo prebuild)
        run: npx expo prebuild --platform android --no-install

      - name: Comprobar que HTTP solo se permite a 127.0.0.1 y localhost
        run: |
          M=android/app/src/main/AndroidManifest.xml
          X=android/app/src/main/res/xml/network_security_config.xml
          grep -q 'android:networkSecurityConfig="@xml/network_security_config"' "$M"
          if grep -q 'android:usesCleartextTraffic="true"' "$M"; then echo "HTTP abierto global: no permitido"; exit 1; fi
          test -f "$X"
          test "$(grep -c '<domain ' "$X")" = "2"
          grep -q '127.0.0.1' "$X"
          grep -q 'localhost' "$X"

      - uses: actions/cache@v4
        with:
          path: |
            ~/.gradle/caches
            ~/.gradle/wrapper
          key: gradle-${{ runner.os }}-${{ hashFiles('app_fuente/package.json', 'app_fuente/package-lock.json') }}
          restore-keys: gradle-${{ runner.os }}-

      # La plantilla de Expo firma el release con la clave de depuracion incluida en la plantilla:
      # no hay ninguna clave real en el repo. Solo arm64 y armv7 (los telefonos), para ir mas rapido.
      - name: Compilar el APK (release)
        working-directory: app_fuente/android
        run: |
          chmod +x ./gradlew
          ./gradlew assembleRelease --no-daemon --stacktrace -PreactNativeArchitectures=arm64-v8a,armeabi-v7a -Dorg.gradle.jvmargs=-Xmx4g

      - name: Preparar el APK
        id: apk
        run: |
          SRC=$(find android/app/build/outputs/apk/release -name '*.apk' | head -n1)
          [ -n "$SRC" ] || { echo "No se genero ningun APK"; exit 1; }
          VER=$(node -p "(require('./app.json').expo || {}).version || '0.0.0'")
          mkdir -p "$GITHUB_WORKSPACE/dist"
          NAME="Neurotok-${VER}-${GITHUB_SHA::7}.apk"
          OUT="$GITHUB_WORKSPACE/dist/$NAME"
          cp "$SRC" "$OUT"
          APKSIGNER=$(ls -d "$ANDROID_HOME"/build-tools/*/apksigner 2>/dev/null | sort -V | tail -n1 || true)
          if [ -n "$APKSIGNER" ]; then
            "$APKSIGNER" verify --print-certs "$OUT" | tee /tmp/cert.txt
            grep -qi "Android Debug" /tmp/cert.txt || echo "AVISO: la firma no es la de depuracion de Expo"
          fi
          {
            echo "### APK listo"
            echo "- Archivo: \`$NAME\` ($(du -h "$OUT" | cut -f1))"
            echo "- SHA-256: \`$(sha256sum "$OUT" | cut -d' ' -f1)\`"
            echo "- Bajalo abajo, en **Artifacts** (viene dentro de un zip)."
          } >> "$GITHUB_STEP_SUMMARY"

      - uses: actions/upload-artifact@v4
        with:
          name: neurotok-apk
          path: dist/*.apk
          if-no-files-found: error
          retention-days: 14
          compression-level: 0
'''


def fallar(msg):
    sys.exit("[ERROR] " + msg + "\nNo se escribio nada.")


# ------------------------------------------------------------------ 1) comprobar el terreno
if not (R / "backend").is_dir() or not APP.is_dir():
    fallar("Ejecuta esto desde ~/neurotok (con backend/ y app_fuente/).")
for f in ("package.json", "app.json"):
    if not (APP / f).exists():
        fallar(f"falta app_fuente/{f}. Copia el proyecto Expo: cp app/{f} app_fuente/ (o corre fase_d1.py).")
faltan = [a for a in ("icon.png", "adaptive-icon.png", "logo.png") if not (APP / "assets" / a).exists()]
if faltan:
    fallar(f"faltan en app_fuente/assets/: {', '.join(faltan)}")

pkg = json.loads((APP / "package.json").read_text(encoding="utf-8"))
deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
for d in ("expo", "react-native", "react-native-svg", "@react-native-async-storage/async-storage"):
    if d not in deps:
        fallar(f"falta {d} en app_fuente/package.json. Instalalo con: cd app_fuente && npx expo install {d}")
m = re.search(r"(\d+)", deps["expo"])
sdk = int(m.group(1)) if m else 0
if sdk and sdk < 52:
    print(f"[AVISO] Expo SDK {sdk}: el workflow usa Node 22 y JDK 17, pensados para SDK 54 o superior.")

# ------------------------------------------------------------------ 2) app.json
cfg = json.loads((APP / "app.json").read_text(encoding="utf-8"))
if "expo" not in cfg:
    cfg = {"expo": cfg}
ex = cfg["expo"]
ex["name"] = "Neurotok"
ex["slug"] = "neurotok"
ex.setdefault("version", "1.0.0")
ex["icon"] = "./assets/icon.png"
andr = ex.setdefault("android", {})
andr.setdefault("package", "com.ivananasco4.neurotok")
andr.setdefault("versionCode", 1)
adapt = andr.setdefault("adaptiveIcon", {})
adapt["foregroundImage"] = "./assets/adaptive-icon.png"
adapt["backgroundColor"] = FONDO

plugins = ex.setdefault("plugins", [])
nombre = lambda p: p[0] if isinstance(p, list) else p  # noqa: E731
if "./plugins/withLocalhostCleartext" not in [nombre(p) for p in plugins]:
    plugins.append("./plugins/withLocalhostCleartext")

splash = {"image": "./assets/logo.png", "backgroundColor": FONDO}
if "expo-splash-screen" in deps:   # SDK moderno: el splash se configura como plugin
    for i, p in enumerate(plugins):
        if nombre(p) == "expo-splash-screen":
            props = dict(p[1]) if isinstance(p, list) and len(p) > 1 else {}
            props.update({**splash, "imageWidth": props.get("imageWidth", 200)})
            plugins[i] = ["expo-splash-screen", props]
            break
    else:
        plugins.append(["expo-splash-screen", {**splash, "imageWidth": 200}])
    via = "plugin expo-splash-screen"
else:                              # SDK sin ese paquete: clave "splash" clasica
    ex["splash"] = {**ex.get("splash", {}), **splash, "resizeMode": "contain"}
    via = "clave splash"

# ------------------------------------------------------------------ 3) escribir
(APP / "plugins").mkdir(exist_ok=True)
(APP / "plugins" / "withLocalhostCleartext.js").write_text(PLUGIN, encoding="utf-8")
(APP / "app.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
wf = R / ".github" / "workflows"
wf.mkdir(parents=True, exist_ok=True)
(wf / "ci.yml").write_text(CI, encoding="utf-8")
(wf / "apk.yml").write_text(APK, encoding="utf-8")

# ------------------------------------------------------------------ 4) comprobar lo escrito
try:
    import yaml
    for f in ("ci.yml", "apk.yml"):
        yaml.safe_load((wf / f).read_text(encoding="utf-8"))
    print("YAML valido")
except ImportError:
    print("(PyYAML no esta instalado: el YAML no se pudo comprobar aqui; GitHub lo comprobara)")
if shutil.which("node"):
    r = subprocess.run(["node", "--check", str(APP / "plugins" / "withLocalhostCleartext.js")],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit("[ERROR] el plugin no pasa la sintaxis:\n" + r.stderr)
print(f"Tarea 1 aplicada. Expo SDK {sdk or '?'}; splash por {via}; app: Neurotok ({andr['package']}).")
