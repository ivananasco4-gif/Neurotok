# CONFIRMACIÓN · Tarea 2 · Pestañas Chat y Terminal (rama `feat/chat-ui`)

## Qué se hizo
- **Pestañas:** `Chat · Terminal · Lienzo · Bóveda · Ajustes`. La pestaña inicial pasó de Lienzo a **Chat** (es la vía principal). Lienzo, Bóveda y Ajustes no se tocaron (el lanzador de objetivos de Ajustes sigue ahí).
- **`src/Chat.js`:** burbujas `tu` (clara, a la derecha) / `cerebro` (panel, a la izquierda) / `sistema` (centrado, cursiva). Franja superior: "Tarea en curso · paso x/y" o "Sin tarea en curso · tu próximo mensaje será un objetivo nuevo". Consulta `GET /chat?desde=N` cada 0,8 s; envía con `POST /chat {texto}`.
- **`src/Terminal.js`:** log monoespaciado con **Filtrada / Cruda** (usa `crudo` si existe; si es `null` muestra `texto`). Interruptor **Manual / Auto** (`POST /modo`). Cola de aprobación: tarjeta con el comando en un campo **editable** y los botones *Ejecutar* (manda el original; si editaste el texto se llama "Ejecutar original"), *Editar y ejecutar* (manda `cmd` editado) y *Rechazar* (pide motivo opcional y luego "Confirmar rechazo"). Línea de comandos propios **deshabilitada** salvo `exec_habilitado: true`. Consulta `/terminal` y `/pending` cada 0,8 s.
- **Riesgo (`riesgo:true`):** etiqueta "⚠ RIESGO" en bloque claro/invertido (forma y texto, sin color nuevo) y **segundo toque** ("¿Seguro? Toca otra vez") antes de ejecutar. Esto último no estaba en el pedido; es solo UI y se quita fácil.
- **Color:** solo `src/theme.js`. El violeta se usa únicamente en el borde de las tarjetas por aprobar y en el punto de "Tarea en curso".
- **`src/api.js`:** se añadió al final `liveApi(base)` con las 8 llamadas del contrato (`Authorization: Bearer`). Errores legibles: 401 → "Token incorrecto: revisa Ajustes"; 403 de `/exec` → el mensaje del servidor ("terminal manual desactivada"); sin red → "Sin conexión con el servidor…". Lo existente de `api.js` no cambió.
- **`src/mock.js`:** se añadió al final `demoApi` (misma forma que `liveApi`). Demo: cola de 3 comandos (el 3.º, `rm -rf …`, es de riesgo), respuestas del cerebro, modo Auto (ejecuta lo seguro y deja el de riesgo esperando), terminal manual habilitada. Lo existente de `mock.js` no cambió.
- **Polling solo con la pestaña abierta:** `App.js` ya desmonta la pestaña al cambiar, y el `setInterval` se limpia al desmontar.

## Qué se probó (en Linux, no en Termux ni en el teléfono)
- `fase_2.py` contra una **reconstrucción** de `app_fuente/` hecha con el `neurotok_src.txt` que subiste: aplica, es idempotente (2.ª corrida = "sin cambio") y si `App.js` no coincide **aborta sin tocar nada**. El diff de `App.js` son 7 líneas.
- 15 pruebas con node (`python fase_2.py probar`): lógica del Demo (cola, aprobar original/editado, rechazar con motivo, id inexistente, modo auto, cursores `desde/siguiente`) y cliente real con `fetch` simulado (URL, cuerpo y cabecera de cada llamada, 401, 403, sin red, respuesta vacía).
- Revisión estructural de paréntesis/llaves/etiquetas de `Chat.js` y `Terminal.js`.

## Qué NO se probó
- **La sintaxis JSX no se compiló aquí** (sin acceso a npm). Es el paso crítico: `python fase_2.py probar` lo hace con `esbuild` en Termux.
- **No se vio nada en pantalla**: ni en Expo Go ni en el teléfono. Pueden necesitar ajuste: tamaño de las 5 pestañas en la barra inferior, altura de la cola (tope 48 % de la pantalla), comportamiento del teclado en Android.
- **Nada contra el backend real**: aún no existe. Solo se probó contra el contrato escrito en el documento.

## Supuestos sobre el backend (para quien lo implemente)
1. `GET /chat` devuelve también los mensajes `tu` (la app **no** pinta el tuyo hasta que el servidor lo devuelve).
2. `n` crece sin huecos y `siguiente` = último `n` + 1; si `siguiente` baja, la app entiende que el servidor se reinició y empieza de cero.
3. En modo **auto**, lo que tiene `riesgo:true` debería seguir pidiendo aprobación (así se comporta el Demo). La app no lo impone.
4. `approve`/`reject` sobre un `id` que ya no existe: cualquier error con `{"error": "..."}` se muestra tal cual.
5. Los POST pueden responder cualquier JSON (o vacío); la app solo mira el código HTTP.

## Cambios necesarios en archivos reservados
Ninguno.

## Si falla, pásame
- La salida completa de `python fase_2.py probar` (sobre todo las líneas `FALLA  sintaxis`).
- Si compila pero se ve mal: captura de pantalla de la pestaña y dime en qué modo estabas (Demo o API real).
