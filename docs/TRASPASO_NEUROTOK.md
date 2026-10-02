# Traspaso del proyecto Neurotok

## Prompt para pegar a la otra IA
> Eres un ingeniero senior (Python 3 + React Native/Expo). Vas a continuar el proyecto **Neurotok**. Lee este documento completo antes de escribir código. El usuario trabaja solo desde un teléfono Android con Termux (sin PC) y habla español. Respeta las reglas de las secciones 2 y 5. Tu tarea está en la sección 8. Entrega todo según la sección 9.

Repo público: https://github.com/Ivananasco4-gif/Neurotok (rama `main`).

## 1. Qué es
Cerebro autónomo multi-agente que corre en Termux. Flujo: el humano ("cerebelo") da una tarea → Gemini (cerebro) la reparte en subtareas → sub-cerebros (Arquitecto, Creador, Auditor) → neuronas (APIs de IA gratuitas, luego instancias de OmniRoute) → comandos bash ejecutados en Termux → salida cruda → filtro Markdown (sanitizador) → bóveda Markdown (`~/boveda_ia/`) → vuelta a la IA. Objetivo: ahorrar >90% de tokens y poder rotar de IA cuando una se queda sin cuota. Una app Expo (React Native) es el dashboard.

## 2. Reglas de trabajo con el usuario
- Español, trato de "tú", respuestas cortas (se lee en teléfono). Explica en simple.
- Sin zips ni muchos archivos. Entrega **un solo script `.py` aplicador** (ver sección 9) y **un solo bloque de comandos** para Termux.
- Prueba lo que puedas antes de entregar y di con honestidad qué no pudiste probar.
- Estilo visual: negro mate tipo n8n, cuadrícula milimétrica, nodos gris frío casi blanco, **sin colores de estado**; el estado se marca por forma. El **violeta oscuro (#6d28d9) es solo para el flujo en vivo**. La marca (logo azul/cian/violeta) solo en la pantalla de entrada y la cabecera.
- Decisiones ya tomadas: Termux queda como app aparte (no se incrusta); el dashboard consulta cada 0.5 s (sin WebSocket); `session_token` de cuentas web no se admite (solo `api_key`); no se oculta ni suaviza ninguna advertencia de seguridad.

## 3. Arquitectura y archivos
```
neurotok/
├── instalar.sh  iniciar_app.sh  iniciar_backend.sh  iniciar_simulado.sh  LEEME.md
├── .githooks/pre-commit        # bloquea claves y cuentas.json (core.hooksPath=.githooks)
├── backend/                    # Python 3, solo requests + librería estándar
│   ├── sanitizer.py            # quita ANSI/progreso, trunca (5 primeras + 10 últimas), redact() de secretos, register_secrets()
│   ├── vault_manager.py        # ~/boveda_ia: 00_estado_actual.md (<200 tokens), 01_bitacora.md, metrics.json
│   ├── worker_pool.py          # Neurona, WorkerPool (DISPONIBLE/TRABAJANDO/EN_PAUSA, cooldown), call_llm() por proveedor
│   ├── agent_loop.py           # AgentLoop.run(), RUNTIME (estado compartido), BLOCKED/RISKY, subprocess con timeout
│   ├── api_server.py           # http.server (sin FastAPI: pydantic-core no compila en Termux)
│   ├── cuentas.example.json    # plantilla; cuentas.json real está en .gitignore
│   └── cuentas.simulado.json   # IA falsa con guion para probar sin API keys
├── app_fuente/                 # código fuente de la app (se copia a app/)
│   ├── App.js  src/{Canvas,layout,mock,api,theme,vaultOps}.js  assets/*.png
└── app/                        # lo genera create-expo-app; NO está en git (cp app_fuente/* app/)
```
Dependencias de la app: `react-native-svg`, `@react-native-async-storage/async-storage` (instaladas con `npx expo install`).
Proveedores en `call_llm`: gemini, claude, groq, deepseek, grok, qwen, kimi (estos tres últimos y groq/deepseek/grok son compatibles con OpenAI) y `simulado`.
Variables de entorno: `NEUROTOK_CUENTAS`, `NEUROTOK_TOKEN_FILE`, `BOVEDA_DIR`, `WORKDIR` (default `~/proyectos_ia`), `CMD_TIMEOUT` (120), `NEUROTOK_ALLOW_RISKY=1`.

## 4. API (127.0.0.1:8000, siempre con `Authorization: Bearer <token>`; token en `~/.neurotok_token`)
- `GET /status` → `{objetivo, estado, progreso_pct, paso_actual, total_pasos, iteracion, neurona_activa, error}`
- `GET /neurons` → `{neuronas:[{id, proveedor, rol, estado, cooldown_restante_s, usos, errores, sub_cerebro}], sub_cerebros}`
- `GET /flow` → `{etapas:[{nombre, activa}] (6 etapas), comando_activo, ahorro_pct, consola_md}`
- `GET /boveda` → `{estado_actual_md, metricas:{tokens_crudos_aprox, tokens_limpios_aprox, ahorro_pct}}`
- `POST /run {objetivo}`, `POST /stop`
Roles de neurona: `orquestador`, `arquitecto`, `creador`, `auditor`.

## 5. Seguridad (no romper)
Repo público: **nunca** subir claves. La API exige token (comparación `hmac.compare_digest`), escucha solo en 127.0.0.1, sin CORS, valida `Host`, límite de cuerpo 4096. El sanitizador tapa claves antes de bóveda/logs/IA. `agent_loop` bloquea siempre: destructivos y acceso a `cuentas.json`, `.ssh`, token, `.env`; y bloquea salvo `NEUROTOK_ALLOW_RISKY=1`: `curl|sh`, `rm -r/-f`, `chmod`, `sudo`, `nc`, `eval`, `base64 -d`. La salida de comandos va a la IA dentro de `<salida_datos>…</salida_datos>` como dato no confiable (anti-inyección). Una terminal manual en la app debe venir **desactivada por defecto**.

## 6. Estado
Hecho: seguridad; sanitizador; bóveda básica; pool con cooldown/rotación ante 429; bucle agéntico; API; app con Lienzo estilo n8n (nodos movibles con posiciones guardadas, chips "MD" en cada conector), Bóveda (Estado / Grafo / Fallidos, **solo en modo Demo**, editable), Ajustes, pantalla de entrada y marca; IA simulada que se probó de punta a punta.
No hecho: lo de la sección 7. Gemini aún no hace de cerebro real (solo hay arquitecto→creador). La "IA lectora" es solo un nodo visual. Los chips MD son visuales. No se ha probado con API keys reales ni en un APK.

## 7. Pendiente (en este orden sugerido)
- **A. Chat + Terminal + aprobación** (pestañas Chat · Terminal · Lienzo · Bóveda · Ajustes). Chat con el cerebro. Terminal: log en vivo con vista filtrada/cruda. Cola de comandos propuestos: Ejecutar / Editar y ejecutar / Rechazar; modo manual por defecto. Endpoints previstos: `GET /terminal?desde=N`, `GET /pending`, `POST /approve {id, cmd}`, `POST /reject {id, motivo}`, `POST /chat`. Las correcciones humanas se guardan en la bóveda (futuro dataset).
- **B. tmux**: la IA escribe/lee en una sesión `tmux` real; marcadores de fin de comando y timeouts.
- **C. Bóveda real (ver sección 8).**
- **D. Cerebro y neuronas**: Gemini reparte subtareas por sub-cerebro; proveedor `omniroute` con `url` y clave por instancia (planeado: 5 instancias × ~100 modelos = ~500 neuronas, neurona = instancia+modelo, cooldown por modelo y por instancia); distinguir límite de ritmo (segundos) de cuota agotada (horas); IA lectora (solo salidas largas o con error); en el lienzo mostrar 5 nodos de instancia con contadores, no 500 nodos. Los límites gratis son de cada proveedor, no de OmniRoute.
- **E. IA propia (último)**: exportar la bóveda como JSONL (tarea, contexto, comando, resultado) y, si hay cientos de ejemplos verificados, afinar un modelo chico en una GPU gratuita. Antes: recuperación de ejemplos y "recetas" (comandos que funcionaron N veces se proponen directo).

## 8. Reparto sugerido para la otra IA: **C. Bóveda real** (rama `feat/boveda`)
1. Guardar de forma estructurada tareas → pasos → comandos (archivo JSON o SQLite en `~/boveda_ia/`), con estado `ok|fallo|en_curso` y `exit`.
2. **Reserva de fallidos**: comando, error resumido, tarea, veces, solución, `rehabilitado`. Solo errores permanentes (comando inexistente, módulo faltante, sintaxis); no timeouts, red ni 429. Antes de pedir a la IA se le pasan los fallidos relevantes ("no repetir") y el ejecutor rechaza comandos idénticos.
3. **Archivador estilo Obsidian**: notas `.md` en `~/boveda_ia/proyectos/<proyecto>/` con etiquetas y `[[enlaces]]`. Reconocer el mismo proyecto primero por carpeta de trabajo/repo git; si no, por similitud de palabras; si duda, preguntar.
4. **Buscar primero en la bóveda** (SQLite FTS5): inyectar 2–3 fragmentos cortos al prompt; medir y publicar el ahorro real en `metricas`.
5. Endpoints nuevos: `GET /boveda/grafo` → `{tareas:[{id,titulo,estado,pasos:[{id,titulo,estado,comandos:[{id,cmd,exit,estado}]}]}]}`, `GET /boveda/fallidos` → `[{id,cmd,error,tarea,veces,solucion,rehabilitado}]`, y `POST` para editar/borrar/rehabilitar. **Esas formas son las de `demoVault()` en `app_fuente/src/mock.js`**; cuando existan, hay que conectar `Boveda` en `App.js` en modo API (hoy muestra un aviso).
6. Para no chocar con la tarea A: tocar sobre todo `vault_manager.py` (módulo nuevo `archivador.py` si hace falta) y solo añadir llamadas mínimas en `agent_loop.py`.

## 9. Cómo entregar
Un script `faseX.py` que se ejecuta desde `~/neurotok` y aplica los cambios con reemplazos exactos (falla si el texto no coincide; idempotente) o reescribe archivos completos. Después, **un solo bloque** de comandos para Termux (copiar, instalar dependencias con `pip`/`npx expo install`, `git add/commit/push`). Pruebas previas obligatorias: `python -m py_compile backend/*.py`, y para la app comprobar la sintaxis JSX. Las dependencias nativas de Python (como `pydantic-core`) no se compilan en Termux: usa solo `requests` y la librería estándar.

## 10. Cuidado
No reintroducir FastAPI. No subir `backend/cuentas.json`. Mantener `app_fuente/` como fuente de verdad (la carpeta `app/` se regenera). Expo Go no muestra el ícono ni el splash nativo. Si el arrastre de nodos vuelve a tener lag: mantener los `memo`, la animación por pasos y el throttle con `requestAnimationFrame`.
