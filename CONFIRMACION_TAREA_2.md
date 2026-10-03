# Neurotok — Confirmación Tarea 2

## Qué se hizo
- Añadidas las pestañas `Chat` y `Terminal` sin eliminar Lienzo, Bóveda ni Ajustes.
- `Chat`: conversación `tu` / `cerebro` / `sistema`, envío de objetivos y polling mientras la pestaña está abierta.
- `Terminal`: log filtrado/crudo, cola de aprobación editable, Ejecutar / Editar y ejecutar / Rechazar, modo manual/auto y ejecución manual condicionada por `exec_habilitado`.
- Añadidos los endpoints de la API definidos para Chat y Terminal.
- Añadido Demo con conversación simulada y tres comandos pendientes, incluido uno marcado como riesgo.
- Se mantuvo el tema existente: negro mate, grises fríos y sin colores de estado nuevos; el riesgo se marca por texto/forma.

## Qué se probó
- Revisión estática de los archivos generados y de los contratos de endpoints contra `docs/TRASPASO_NEUROTOK.md`.
- Comprobación de que los cambios de `App.js` solo registran las nuevas pestañas/componentes y conservan Lienzo, Bóveda y Ajustes.

## Qué NO se pudo probar
- No se ejecutó Expo Go en un teléfono real desde este entorno.
- No se ejecutó `esbuild`/Metro aquí con las dependencias completas del proyecto.
- No se probó contra un backend real porque la implementación del contrato corresponde a otra tarea.
- No se probó una respuesta HTTP 401/403 real; sí quedó manejo explícito del 401 y de errores de red.

## Supuestos
- El backend implementará exactamente los endpoints y formas indicados en la Tarea 2.
- `Authorization: Bearer <token>` continúa siendo gestionado por `auth` en `api.js`.
- El polling se limita a 700 ms y se detiene al desmontar la pestaña.

## Archivos reservados
No se modificaron `backend/agent_loop.py`, `backend/worker_pool.py` ni `backend/prompt_filter.py`.
No se requiere cambio en ellos para esta tarea.
