# Cerebro ↔ neuronas conectados

## Qué cambia
- **El cerebro (Gemini, rol `orquestador`) planifica y asigna** cada paso a un sub-cerebro:
  `{"pasos":[{"titulo","sub_cerebro":"arquitecto|creador|auditor"}]}`. El formato antiguo (`["texto"]`) sigue valiendo (va a `creador`).
- **Cada paso lo ejecutan las neuronas de su sub-cerebro.** Tras 2 fallos seguidos entra el `auditor`.
- **La cuota del cerebro se reserva:** si no hay neurona del rol pedido, trabaja otra neurona cualquiera; Gemini solo como último recurso.
- **OmniRoute `"rol_sugerido": "auto"`**: los modelos de la instancia se reparten entre creador/auditor/arquitecto (mitad creadores).
- `/status` añade `sub_cerebro_activo` y `plan` (`titulo`, `sub_cerebro`, `estado`, `neuronas` que lo trabajaron). `/flow` añade `sub_cerebro_activo` y `neurona_activa`.
- **Lienzo:** las neuronas OmniRoute se dibujan como **un nodo por instancia** bajo cada sub-cerebro (libres/total, la que trabaja o la próxima pausa). 502 neuronas → 26 nodos. Las directas siguen sueltas (máx. 6).

## Probado (offline)
- `tests/test_cerebro_neuronas.py`: punta a punta con IA simulada; cada paso lo trabaja su sub-cerebro, Gemini no ejecuta, rotación ante 429.
- `tests/test_layout.mjs`: ≤ 40 nodos con 500 neuronas, sin NaN ni solapes, ids estables.
- Todos los tests anteriores siguen en verde; se añadieron al CI.

## No probado
- Con Gemini y OmniRoute reales (sin claves aquí).
- Sintaxis JSX de `App.js` con esbuild: la comprueba el CI.
