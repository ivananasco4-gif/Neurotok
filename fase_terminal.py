#!/usr/bin/env python3
"""fase_terminal.py - La Terminal "Filtrada" muestra la salida limpia, no el bloque Markdown del sanitizador.
Causa: consola.salida() guardaba en `texto` el Markdown que se manda a la IA ("### Comando ejecutado",
"**exit_code:**", vallas ```). Ahora `texto` = salida limpia con la misma limpieza del sanitizador
(clean_lines + truncate) y `crudo` = salida sin filtrar con las claves tapadas.
Solo toca backend/consola.py (reemplazos exactos, idempotente). La app NO cambia: Terminal.js ya muestra
`texto` en Filtrada y `crudo` en Cruda. Ejecutar desde ~/neurotok y reiniciar el backend."""
import pathlib
import py_compile
import sys

RUTA = pathlib.Path("backend/consola.py")
if not RUTA.exists():
    sys.exit("Ejecuta esto desde ~/neurotok")

PARCHES = [
    ('    def salida(self, cmd: str, code: int, out: str, err: str, to: bool, md: str = "") -> None:\n        md, out, err = _sin_tags(_limpiar(md)), _limpiar(out or ""), _limpiar(err or "")\n        if md or out.strip():\n            self.terminal.add(tipo="out", texto=_recortar(md or out, 8000), crudo=_recortar(out, 8000))\n        if err.strip():\n            self.terminal.add(tipo="err", texto=_recortar(err, 1500), crudo=_recortar(err, 8000))\n        fin = f"exit {code}" + (" (timeout)" if to else "")\n        self.terminal.add(tipo="info", texto=fin, crudo=fin)\n', '    def salida(self, cmd: str, code: int, out: str, err: str, to: bool, md: str = "") -> None:\n        # `md` (el bloque Markdown que se manda a la IA) se conserva en la firma por compatibilidad, pero ya\n        # no se muestra: la vista "Filtrada" enseña la salida limpia y la "Cruda" la salida tal cual.\n        for tipo, bruto, tope in (("out", out, 8000), ("err", err, 3000)):\n            limpio, crudo = _filtrar(bruto, tope), _cruda(bruto)\n            if not crudo.strip():\n                continue  # sin salida: basta la linea "exit N"\n            self.terminal.add(tipo=tipo, texto=limpio.strip() and limpio or "(solo ruido de progreso omitido)",\n                              crudo=crudo)\n        fin = f"exit {code}" + (" (timeout)" if to else "")\n        self.terminal.add(tipo="info", texto=fin, crudo=fin)\n'),
    ('def _hora() -> str:\n', 'try:  # el sanitizador del proyecto: la misma limpieza que recibe la IA, pero sin el envoltorio Markdown\n    from sanitizer import clean_lines, strip_ansi, truncate\nexcept Exception:  # noqa: BLE001\n    clean_lines = strip_ansi = truncate = None\n\n\ndef _cruda(texto: str) -> str:\n    """Salida tal cual (con claves tapadas); solo se quitan colores y el \\\\r\\\\n, que la app no sabe pintar."""\n    t = _limpiar(texto or "")\n    if strip_ansi:\n        try:\n            t = strip_ansi(t)\n        except Exception:  # noqa: BLE001\n            pass\n    return _recortar(t.replace("\\r\\n", "\\n"), 8000)\n\n\ndef _filtrar(texto: str, tope: int) -> str:\n    """Salida limpia para la vista Filtrada: sin colores ni barras de progreso, sin repeticiones y recortada\n    como hace el sanitizador (5 primeras + 10 ultimas lineas). Sin cabeceras ni vallas Markdown."""\n    t = _limpiar(texto or "")\n    if clean_lines and truncate:\n        try:\n            t = "\\n".join(truncate(clean_lines(t)))\n        except Exception:  # noqa: BLE001\n            pass\n    return _recortar(t.rstrip(), tope)\n\n\ndef _hora() -> str:\n'),
]
txt = RUTA.read_text(encoding="utf-8")
for i, (viejo, nuevo) in enumerate(PARCHES, 1):
    if nuevo in txt:
        continue
    if txt.count(viejo) != 1:
        sys.exit(f"[ERROR] consola.py: el parche {i} no coincide ({txt.count(viejo)} veces). No se toco nada.")
    txt = txt.replace(viejo, nuevo)
RUTA.write_text(txt, encoding="utf-8")
py_compile.compile(str(RUTA), doraise=True)
print("Terminal filtrada corregida. Reinicia el backend.")
