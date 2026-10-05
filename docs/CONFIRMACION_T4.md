# Confirmación · Tarea 4 (OmniRoute) — ENTREGA PARCIAL

## Qué se hizo (probado offline, sin red ni claves)
- `backend/errores_llm.py`: `clasificar_error(status, headers, body, proveedor)` puro. Cubre OpenAI (`rate_limit_exceeded` vs `insufficient_quota`), Gemini (`RESOURCE_EXHAUSTED`, `retryDelay`, `PerDay` => cuota), Groq (`retry-after`, "try again in 7m12s", TPD), `Retry-After` en segundos/fecha HTTP, 401/403, 404/model_not_found, 5xx/caída.
- `backend/omniroute.py`: `listar_modelos` (GET `{url}/models`, filtra no-chat), `chat`, y `PoolOmniRoute` (neurona = `instancia/modelo`, cooldown por modelo y por instancia, menos usadas primero, rotación inmediata, `acquire/release/cooldown/snapshot`, `resumen()` con la forma de `/neurons/resumen`).
- `tests/test_omniroute.py`: servidor falso con `/models`, OK, 429 ritmo, 429 cuota, 404 modelo y caída de instancia. Resultado: **OK**.

## Verificado en documentación pública de OmniRoute
URL base `http://HOST:20128/v1`; autenticación `Authorization: Bearer <clave de gateway>` (se crea en Dashboard → API Keys; con `REQUIRE_API_KEY` activo, `/v1/models` da 401 sin clave); `/v1/chat/completions` compatible OpenAI. **No verificado:** el formato exacto de sus errores 429 (uso reglas genéricas) ni si `/models` trae campo de tipo (el filtro es por nombre y por campos si existen).

## NO hecho (no tengo tu repo)
No pude leer `worker_pool.py` ni `api_server.py`, así que **no los toqué** ni hice `fase_t4.py`. Falta:
1. Integrar `PoolOmniRoute` en `worker_pool.py` con tus firmas reales de `acquire/release/cooldown/snapshot`.
2. `/neurons` con `instancia` y `GET /neurons/resumen` en `api_server.py`.
3. Usar `clasificar_error` en Gemini/Groq directos.
Pásame esos dos archivos (o su contenido) y lo cierro con aplicador idempotente.

## Guía rápida (conectar tu instancia)
1. Instala OmniRoute en su host y abre su Dashboard.
2. Dashboard → Providers: añade tus proveedores con **tus** claves.
3. Dashboard → API Keys: crea una clave de gateway.
4. Prueba: `curl -H "Authorization: Bearer CLAVE" http://HOST:20128/v1/models`.
5. Copia `cuentas.omniroute.example.json` dentro de `backend/cuentas.json` con tu URL y clave.
6. Una entrada por instancia (`id` distinto); `modelos: "auto"` los descubre.
7. Nunca subas `cuentas.json` al repo.
8. Reinicia el backend y mira `/neurons`.

## Honestidad sobre límites
Los límites gratuitos son de cada proveedor, no de OmniRoute. Varias instancias con las mismas claves **no suman cuota**; este código solo reparte y respeta pausas, no crea cuentas ni elude límites.
