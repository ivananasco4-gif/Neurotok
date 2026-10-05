# Neurotok · Segunda tanda: 3 tareas en paralelo (para 3 IAs distintas)

Cada tarea va a **una IA distinta**. No se pisan: tocan archivos distintos. Contexto general: `docs/TRASPASO_NEUROTOK.md` y `docs/TAREAS_PARALELAS_NEUROTOK.md` (primera tanda). Repo: https://github.com/Ivananasco4-gif/Neurotok (rama `main`). Léelos primero; este documento los actualiza.

## Estado actual (octubre 2026)
- `main` incluye: seguridad base, sanitizador, bóveda real (SQLite+FTS5, fallidos, archivador estilo Obsidian), Lienzo estilo n8n con nodos movibles y chips "MD", dos cerebros (Gemini y Groq, ambos rol `orquestador`), filtro Markdown de entrada, **Chat, Terminal y aprobación de comandos** (app + backend), `tmux_session.py`, prompts de pasos mínimos y workflows de GitHub (`ci.yml`, `apk.yml`, aún sin confirmar que compilen).
- **Primera prueba completa en el teléfono hecha:** app (Expo Go) ↔ backend real ↔ Gemini/Groq reales. Modo manual con aprobación: funciona. El usuario no tiene todavía OmniRoute conectado.
- API actual (siempre con `Authorization: Bearer <token>`): `/status /neurons /flow /boveda /boveda/grafo /boveda/fallidos`, `POST /boveda/editar|borrar|rehabilitar|proyecto`, `/run /stop`, `/terminal /pending /approve /reject /modo /exec /chat /correcciones`.
- Variables de entorno: `NEUROTOK_MODO`, `NEUROTOK_EXEC`, `NEUROTOK_TMUX`, `NEUROTOK_APROBACION_MIN`, `NEUROTOK_FILTRO`, `NEUROTOK_ALLOW_RISKY`, `NEUROTOK_CUENTAS`, `BOVEDA_DIR`, `WORKDIR`, `CMD_TIMEOUT`.
- **Archivos reservados (NO modificar; los toca otra persona):** `backend/consola.py`, `backend/agent_loop.py`, `app_fuente/src/Terminal.js`, `app_fuente/src/Chat.js`. Si necesitas un cambio ahí, descríbelo al final de tu entrega como parche exacto y se integra aparte.
- Usuario: solo teléfono Android + Termux, sin PC. Español, trato de "tú", respuestas cortas. Sin FastAPI. Nunca subir `backend/cuentas.json` ni claves. Estilo visual: negro mate, gris frío, violeta oscuro solo para flujo en vivo.

## Cómo entregar (las 3 tareas)
1. Trabaja en tu rama (indicada abajo).
2. Un único aplicador `fase_<tarea>.py` idempotente (reemplazos exactos o archivos completos; si algo no coincide, no toca nada y avisa). **Nunca** sobrescribas un archivo ajeno sin comprobar que existe tal como esperas.
3. Un único bloque de comandos para Termux (aplicar, probar, `git add/commit/push` a tu rama).
4. Un `CONFIRMACION_<TAREA>.md`: qué se hizo, **qué se probó y qué NO**, supuestos y parches pendientes para archivos reservados.
5. Los tests que escribas deben correr **sin red y sin claves** (usa servidores falsos locales). Di con honestidad qué no pudiste probar en Termux real.

---

## TAREA 4 · OmniRoute como proveedor, pool por instancias y clasificador de errores  (rama `feat/omniroute`)
**Objetivo:** que un conjunto de instancias de OmniRoute (gateway compatible con OpenAI que el usuario instala por su cuenta, p. ej. `http://HOST:20128/v1`) funcione como "neuronas", con cambio automático cuando una se queda sin cuota. Plan del usuario: unas 5 instancias × ~100 modelos = ~500 neuronas. **Verifica en la documentación oficial de OmniRoute** la URL base, la autenticación y el listado de modelos; no supongas.
**Archivos permitidos:** `backend/worker_pool.py`, nuevos `backend/omniroute.py` y `backend/errores_llm.py`, `backend/cuentas.example.json`, un `GET /neurons/resumen` mínimo en `backend/api_server.py`, tests nuevos en `tests/`.
**Requisitos:**
- Esquema nuevo en `cuentas.json` (retrocompatible con las cuentas actuales): `{"id","proveedor":"omniroute","tipo_auth":"api_key","credencial":"...","url":"http://host:20128/v1","modelos":[...]|"auto","max_modelos":100,"rol_sugerido":"creador"}`. Una **neurona = instancia + modelo** (id `instancia/modelo`). Descubre modelos con `GET {url}/models` y filtra solo los de chat.
- **Cooldown en dos niveles:** por modelo (429/cuota de ese modelo) y por instancia (caída de red, 401/403).
- **Clasificador puro** `clasificar_error(status, headers, body, proveedor) -> ("ritmo"|"cuota"|"auth"|"modelo"|"red"|"otro", segundos)`. Debe distinguir límite de ritmo (segundos) de cuota agotada (horas) con ejemplos realistas: OpenAI-style `rate_limit_exceeded` vs `insufficient_quota`, Gemini `RESOURCE_EXHAUSTED` con `retryDelay`, Groq con `retry-after`, límites diarios. Úsalo también para los proveedores directos que ya existen sin cambiar su comportamiento visible.
- Reparto equilibrado entre neuronas (menos usadas primero) y rotación inmediata ante cuota. Compatible con `acquire/release/cooldown/snapshot` actuales.
- `/neurons` mantiene su forma y añade `instancia` por neurona. Nuevo `GET /neurons/resumen` → `{"instancias":[{"id","nombre","url_corta","total","disponibles","trabajando","en_pausa","proxima_libre_s","ultimo_error"}]}` (la TAREA 5 lo consume).
- **Prohibido** implementar cualquier cosa para crear cuentas o eludir límites de los proveedores. Documenta con honestidad: los límites gratuitos son de cada proveedor, no de OmniRoute, y varias instancias con las mismas claves no suman cuota.
**Aceptación:** un servidor OmniRoute **falso** (`http.server`) en los tests simula `/models`, respuestas OK, 429 por ritmo, 429 por cuota, 404 de modelo y caída; el pool rota correctamente en cada caso. Guía de 10 líneas para que el usuario conecte su instancia.

---

## TAREA 5 · Lienzo escalable: agrupar cientos de neuronas por instancia  (rama `feat/lienzo-escala`)
**Objetivo:** que el Lienzo siga siendo fluido y legible con ~500 neuronas, mostrando **un nodo por instancia con contadores** en lugar de un nodo por neurona.
**Archivos permitidos:** `app_fuente/src/layout.js`, `app_fuente/src/Canvas.js` (solo si hace falta; respeta las reglas de rendimiento ya existentes: `memo`, animación por pasos, `requestAnimationFrame` en el arrastre), `app_fuente/src/mock.js`, `app_fuente/src/api.js`, cambios mínimos en `App.js` y archivos nuevos en `app_fuente/src/`. **No** tocar `Terminal.js` ni `Chat.js`.
**Requisitos:**
- Si las neuronas traen `instancia`, agrúpalas: un nodo por instancia con `total / disponibles / trabajando / en pausa` y la próxima liberación. Las neuronas directas (sin instancia) siguen como hoy mientras sean pocas (≤ 12); si no, se agrupan en un nodo "Directas".
- Tocar un nodo de instancia abre una lista (modal o panel) con sus neuronas, buscable, con estado por forma (aro, punto, punteado) y temporizador de cooldown. Nunca se dibujan más de ~40 nodos en el lienzo.
- Contrato esperado del backend (lo implementa la TAREA 4): `GET /neurons/resumen` → `{"instancias":[{"id","nombre","url_corta","total","disponibles","trabajando","en_pausa","proxima_libre_s","ultimo_error"}]}` y `/neurons` con campo `instancia`. Mientras no exista, calcula el resumen en el cliente a partir de `/neurons`.
- Modo Demo con 5 instancias × 100 neuronas en estados variados que cambian con el tiempo (cooldowns que bajan, 429 simulados).
- Mantén los chips "MD", el estilo (negro mate, violeta solo en flujo vivo) y las posiciones guardadas de nodos movidos.
**Aceptación:** `layout.js` sigue siendo puro y testeable en node (incluye tests: sin solapes, sin NaN, ≤ 40 nodos con 500 neuronas, ids estables al cambiar estados); sintaxis JSX verificada con `esbuild`; sin regresiones en Chat/Terminal/Bóveda/Ajustes.

---

## TAREA 6 · Auditoría de seguridad del proyecto  (rama `feat/seguridad`)
**Objetivo:** el repo es **público** y el sistema ejecuta comandos generados por IA en el teléfono del usuario, así que el riesgo de ejecución remota es el principal. Revisa todo el proyecto con ojos de atacante y entrega un informe y correcciones.
**Alcance a revisar:** `backend/api_server.py`, `consola.py`, `agent_loop.py`, `worker_pool.py`, `sanitizer.py`, `boveda_db.py`, `prompt_filter.py`, `tmux_session.py`, los scripts `.sh`, `.githooks/pre-commit`, `.github/workflows/*`, y en la app cómo se maneja el token.
**Puntos mínimos a cubrir:**
- Autenticación del API, manejo y almacenamiento del token (backend y app), `Host`, CORS, límites de tamaño, ráfagas y consumo de memoria (colas, logs, `correcciones.jsonl`).
- Políticas de comandos: la lista de bloqueo (`BLOCKED`/`RISKY`) es evadible con trucos de shell (`$(...)`, `sh -c`, base64, variables, comodines, `python -c`, enlaces simbólicos). Enumera evasiones **realistas**, qué se puede endurecer en Termux y qué limitaciones deben documentarse con honestidad.
- Carrera/TOCTOU en la aprobación (editar a un comando de riesgo, aprobar dos veces, aprobar tras detener la tarea).
- Rutas y nombres que llegan por API o por la IA y se convierten en archivos o carpetas (`/boveda/proyecto`, `/boveda/editar`, notas Obsidian): path traversal. Consultas FTS5 (`MATCH`) y SQL.
- **Inyección de instrucciones (prompt injection):** salida de comandos, notas de la bóveda y fragmentos recuperados se reinyectan al prompt. ¿Pueden dictar acciones?
- Fugas de secretos: `redact()` en terminal, chat, bóveda, `correcciones.jsonl`, logs, excepciones; historial de git; `cuentas.json` y permisos de archivos (`chmod`).
- GitHub Actions: permisos mínimos del `GITHUB_TOKEN`, riesgos de `pull_request_target`, secretos, versiones fijadas de acciones, firma del APK.
**Entregables:** `AUDITORIA_SEGURIDAD.md` con hallazgos ordenados por gravedad (evidencia con archivo y línea, reproducción **mínima y segura**, impacto, arreglo propuesto), `fase_seg.py` que corrige lo alto y medio **en archivos no reservados**, y parches exactos (diff) para los reservados. Tests offline para cada arreglo. Nada de exploits listos para usar ni de pruebas contra servicios reales.
**Aceptación:** cada hallazgo indica si fue **comprobado** o solo **teórico**; lista aparte de lo que no pudiste revisar; los arreglos no deben romper el flujo actual (modo manual con aprobación sigue funcionando).

---

## En la cola (no empezar todavía)
Medir el ahorro real de tokens con el uso que reportan los proveedores; que el cerebro reparta subtareas entre sub-cerebros; IA lectora; tests automáticos del bucle dentro del repo y en CI; guardar el token de forma segura en la app (`expo-secure-store`); exportar JSONL y "recetas" para una IA propia; confirmar que CI y APK quedan verdes en GitHub.
