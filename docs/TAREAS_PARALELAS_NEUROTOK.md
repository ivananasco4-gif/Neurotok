# Neurotok · 3 tareas en paralelo (para 3 IAs distintas)

Cada tarea se pega a **una IA distinta**. No se pisan: tocan archivos diferentes. Contexto general del proyecto: `docs/TRASPASO_NEUROTOK.md` (en el repo https://github.com/Ivananasco4-gif/Neurotok). Lee ese documento primero; este solo lo actualiza y define la tarea.

## Estado actual (octubre 2026)
- En `main`: seguridad, sanitizador, bóveda real (SQLite+FTS5, fallidos, archivador), Lienzo estilo n8n, Bóveda en la app conectada a la API, dos "cerebros" (Gemini y Groq, ambos rol `orquestador`), filtro Markdown de entrada (`prompt_filter.py`) y workflows de GitHub (`ci.yml`, `apk.yml`, **nunca ejecutados**).
- `app_fuente/` es ahora un proyecto Expo completo (`App.js`, `app.json`, `index.js`, `package.json`, `assets/`, `src/`). El usuario prueba en Expo Go copiando `app_fuente` → `app/` (creada con `create-expo-app`, fuera de git).
- Probado de punta a punta con Gemini + Groq reales: funciona, pero con defectos que **arregla otra persona** (no los toques): pasos que repiten comandos, tarea marcada `fallo` cuando salió bien, el filtro de entrada borra "hola" dentro de una instrucción, y un error de modelo no rota de neurona.
- **Archivos reservados (NO modificar):** `backend/agent_loop.py`, `backend/worker_pool.py`, `backend/prompt_filter.py`. Si necesitas un cambio ahí, descríbelo al final de tu confirmación y se integra aparte.
- Usuario: solo teléfono Android + Termux, sin PC. Español, trato de "tú", respuestas cortas. Sin FastAPI. Nunca subir `backend/cuentas.json` ni claves.

## Cómo entregar (las 3 tareas)
1. Trabaja en tu rama (indicada abajo).
2. Un único script aplicador `fase_<tarea>.py` (idempotente; reemplazos exactos o archivos completos; si algo no coincide, no toca nada y avisa).
3. Un único bloque de comandos para Termux (aplicar, probar, `git add/commit/push` a tu rama).
4. Un `CONFIRMACION_<TAREA>.md` con: qué se hizo, **qué se probó y qué NO**, supuestos, y cambios que necesitas en archivos reservados.
5. Se honesto con lo que no pudiste probar en Termux real.

---

## TAREA 1 · APK por GitHub Actions  (rama `feat/apk`)
**Objetivo:** que desde GitHub (Actions → Run workflow) salga un APK instalable de Neurotok, sin PC.
**Archivos permitidos:** `.github/workflows/*`, `app_fuente/app.json`, `app_fuente/package.json`, plugins de configuración de Expo. **No** tocar `app_fuente/src/` ni `App.js`.
**Requisitos:**
- Corregir/validar `apk.yml` y `ci.yml` (nunca se ejecutaron). Usar `expo prebuild` (Android) + Gradle, con versiones de Node y Java compatibles con el SDK de Expo del `package.json`. Caché de dependencias. Subir el APK como artefacto.
- Nombre de la app **Neurotok**, ícono y splash desde `app_fuente/assets/` (`icon.png`, `adaptive-icon.png`, `logo.png`).
- Firmado con clave de depuración (no subir ninguna clave real al repo).
- La app habla con `http://127.0.0.1:8000`: en Android release el tráfico HTTP está bloqueado por defecto. Permitir **solo** `127.0.0.1` y `localhost` (network security config), nunca HTTP abierto en general.
- Dependencias nativas ya usadas: `react-native-svg`, `@react-native-async-storage/async-storage`.
- `ci.yml` debe quedar verde: `python -m py_compile backend/*.py` y comprobación de sintaxis de la app.
**Aceptación:** YAML válido (usa `actionlint` si puedes), pasos justificados, instrucciones de 5 líneas para el usuario (cómo lanzar el workflow, dónde bajar el APK, cómo instalarlo). Reconoce que no pudiste ejecutarlo y deja una sección "si falla, pásame el log de este paso".

---

## TAREA 2 · Pestañas Chat y Terminal en la app, con aprobación de comandos  (rama `feat/chat-ui`)
**Objetivo:** solo la parte **de la app**; el backend lo implementa otra persona siguiendo el contrato de abajo. La UI debe funcionar completa en **modo Demo** con datos simulados.
**Archivos permitidos:** `app_fuente/App.js` (mínimo: registrar pestañas), nuevos `app_fuente/src/Chat.js`, `src/Terminal.js`, ampliar `src/api.js` y `src/mock.js`. Mantén el tema de `src/theme.js` (negro mate, gris frío, **violeta solo para lo que está pasando en vivo**, sin otros colores).
**Pestañas:** `Chat · Terminal · Lienzo · Bóveda · Ajustes` (las tres últimas ya existen y no deben romperse).
- **Chat:** hablas con el cerebro. Burbujas `tu` / `cerebro` / `sistema`. Si no hay tarea en curso, tu mensaje se toma como nuevo objetivo. Reemplaza al lanzador de objetivos de Ajustes (déjalo, pero el Chat es la vía principal).
- **Terminal:** log en vivo en monoespaciado con interruptor **Filtrada / Cruda**. Cola de aprobación: tarjeta con el comando propuesto en un campo **editable** y tres botones: *Ejecutar*, *Editar y ejecutar* (envía el texto editado), *Rechazar* (con motivo opcional). Interruptor de modo **manual / auto**. Línea para escribir comandos propios, **deshabilitada** salvo que el servidor diga `exec_habilitado: true`.
**Contrato de la API (todo con `Authorization: Bearer <token>`):**
- `GET /terminal?desde=N` → `{siguiente:int, lineas:[{n:int, t:"HH:MM:SS", tipo:"cmd"|"out"|"err"|"info", texto:str, crudo:str|null}]}`
- `GET /pending` → `{modo:"manual"|"auto", exec_habilitado:bool, pendientes:[{id:int, cmd:str, pensamiento:str, paso:int, riesgo:bool}]}`
- `POST /approve {id, cmd?}` (si viene `cmd`, es la versión editada) · `POST /reject {id, motivo?}` · `POST /modo {modo}` · `POST /exec {cmd}` (403 `{"error":"terminal manual desactivada"}` si no está habilitada)
- `GET /chat?desde=N` → `{siguiente:int, mensajes:[{n:int, rol:"tu"|"cerebro"|"sistema", texto:str, t:str}]}` · `POST /chat {texto}` → `{ok:true}`
Consulta cada 0.5–1 s solo mientras la pestaña esté abierta. Maneja errores de red y 401 con un mensaje claro. Un comando con `riesgo:true` se marca visualmente (por forma/texto, no por color nuevo).
**Aceptación:** `esbuild`/sintaxis JSX correcta; el Demo simula una cola con 2–3 comandos (uno de riesgo) y respuestas del cerebro; no hay regresiones en Lienzo/Bóveda/Ajustes; scripts de aplicar y probar.

---

## TAREA 3 · Módulo `tmux_session.py`: ejecutar comandos en una sesión tmux real  (rama `feat/tmux`)
**Objetivo:** un módulo **independiente** que ejecute comandos dentro de una sesión `tmux` visible (el usuario puede mirarla con `tmux attach -t neurotok`) y devuelva el resultado capturado. Se integra después, sin que lo hagas tú, con una variable `NEUROTOK_TMUX=1`.
**Archivos permitidos:** solo nuevos: `backend/tmux_session.py` (y su autoprueba al ejecutar `python backend/tmux_session.py`). **No** tocar `agent_loop.py`. Solo `tmux` + librería estándar de Python (en Termux: `pkg install tmux`).
**API exigida:**
- `available() -> bool` (hay tmux instalado).
- `class TmuxSession(name="neurotok", cwd=None)` con `ensure()` y `run(cmd: str, timeout: int = 120) -> tuple[int, str, str, bool]` = `(exit_code, stdout, stderr, timed_out)`, **la misma forma** que `AgentLoop._execute`. Si no puedes separar stderr, devuélvelo vacío y explica la decisión.
- `close()`.
**Requisitos:** terminación fiable de cada comando con marcadores únicos (no por silencio ni `sleep`); exit code correcto; comandos multilínea, con comillas, heredocs y caracteres especiales sin que el módulo los reinterprete (usa `send-keys -l` o `load-buffer/paste-buffer`); salida grande (≥ 2000 líneas) sin perder el final ni congelarse; timeout que interrumpe (`C-c`) y deja la sesión usable; no dejar procesos huérfanos; si la sesión murió, recrearla. No imprimir ni guardar variables de entorno sensibles. La política de comandos bloqueados la aplica el llamador; no la dupliques, pero no ejecutes nada fuera de lo recibido.
**Aceptación:** autoprueba con al menos: `echo` simple, exit code 0 y distinto de 0, comando inexistente, multilínea con heredoc, 3000 líneas de salida, timeout con `sleep 30` y comando posterior exitoso, y reinicio tras `tmux kill-session`. Di con claridad qué probaste en Linux y qué no en Termux.

---

## En la cola (no empezar todavía)
Proveedor OmniRoute (instancias con URL/clave, ~500 neuronas) + clasificador de errores ritmo/cuota; implementación del backend del contrato de la TAREA 2; IA lectora; exportar JSONL y recetas.
