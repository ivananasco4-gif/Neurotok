"""boveda_db.py - Bóveda estructurada (SQLite + FTS5) y archivador estilo Obsidian.
Solo librería estándar. Un fallo aquí NUNCA debe romper el bucle agéntico."""
from __future__ import annotations

import functools
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

try:  # el sanitizador del proyecto; si no está, se guarda tal cual
    from sanitizer import redact as _redact
except Exception:  # noqa: BLE001
    _redact = None

STOP = set("""para como esta este esto estos estas desde hasta entre sobre cada todo toda todos
todas puede hacer crear usar quiero necesito archivo archivos paso pasos""".split())

# Errores PERMANENTES (el mismo comando nunca va a funcionar)
PERMANENTES = [re.compile(p, re.I) for p in (
    r"command not found", r"no module named", r"modulenotfounderror", r"cannot find module",
    r"syntaxerror", r"syntax error", r"unexpected token", r"unterminated")]
# Errores TRANSITORIOS (red, ritmo, cuota): nunca van a la reserva
TRANSITORIOS = re.compile(
    r"timed? ?out|could not resolve|temporary failure|network is unreachable|connection "
    r"(refused|reset|timed)|\b429\b|rate.?limit|too many requests|quota|unable to connect|"
    r"failed to connect|name resolution|ssl", re.I)


def limpiar(t: str) -> str:
    t = t or ""
    if _redact:
        try:
            return str(_redact(t))
        except Exception:  # noqa: BLE001
            pass
    return t


def _cut(t: str, n: int) -> str:
    t = " ".join((t or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


def tokens(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-záéíóúñü0-9]{4,}", (t or "").lower()) if w not in STOP}


def slug(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-") or "sin-nombre"


def dato(t: str) -> str:
    """Quita las etiquetas que delimitan datos no confiables (anti-inyección)."""
    return (t or "").replace("<salida_datos>", "").replace("</salida_datos>", "")


def es_error_permanente(code: int, stderr: str, timeout: bool = False) -> bool:
    if code == 0 or timeout or code == 124:
        return False
    t = stderr or ""
    if t.startswith(("Comando bloqueado", "Comando rechazado")):
        return False
    if TRANSITORIOS.search(t):
        return False
    return code == 127 or any(p.search(t) for p in PERMANENTES)


def _seguro(default=None):
    def deco(fn):
        @functools.wraps(fn)
        def w(self, *a, **k):
            try:
                return fn(self, *a, **k)
            except Exception as e:  # noqa: BLE001
                print(f"[boveda_db] {fn.__name__}: {e}", file=sys.stderr)
                return default
        return w
    return deco


SCHEMA = """
CREATE TABLE IF NOT EXISTS tareas(id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT, estado TEXT,
  proyecto TEXT DEFAULT '', proyecto_dudoso TEXT DEFAULT '', nota TEXT DEFAULT '', creado REAL, cerrado REAL);
CREATE TABLE IF NOT EXISTS pasos(id INTEGER PRIMARY KEY AUTOINCREMENT, tarea_id INTEGER, titulo TEXT,
  estado TEXT, orden INTEGER);
CREATE TABLE IF NOT EXISTS comandos(id INTEGER PRIMARY KEY AUTOINCREMENT, paso_id INTEGER, cmd TEXT,
  salida INTEGER, estado TEXT, resumen TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS fallidos(id INTEGER PRIMARY KEY AUTOINCREMENT, cmd TEXT UNIQUE, error TEXT,
  tarea TEXT, veces INTEGER DEFAULT 1, solucion TEXT DEFAULT '', rehabilitado INTEGER DEFAULT 0, ts REAL);
CREATE TABLE IF NOT EXISTS proyectos(nombre TEXT PRIMARY KEY, palabras TEXT);
CREATE TABLE IF NOT EXISTS stats(clave TEXT PRIMARY KEY, valor REAL);
"""
TABLAS = {"tarea": "tareas", "paso": "pasos", "comando": "comandos", "fallido": "fallidos"}
EDITABLES = {"tarea": ("titulo",), "paso": ("titulo",), "comando": ("cmd",),
             "fallido": ("solucion", "error", "tarea")}


def _fragmento(cuerpo: str, kw: set[str], n: int = 220) -> str:
    lineas = [x.strip() for x in cuerpo.splitlines() if x.strip()]
    mejores = sorted(lineas, key=lambda x: -len(kw & tokens(x)))
    return _cut(" | ".join(mejores[:2]), n)


def _tocada(carpeta: Path, t0: float) -> bool:
    n = 0
    for raiz, dirs, files in os.walk(carpeta):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".cache")]
        for f in files:
            n += 1
            try:
                if os.path.getmtime(os.path.join(raiz, f)) >= t0 - 1:
                    return True
            except OSError:
                pass
            if n > 3000:
                return False
    return False


class BovedaDB:
    def __init__(self, root) -> None:
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "boveda.db"
        self.lock = threading.RLock()
        with self._tx() as c:
            c.executescript(SCHEMA)
            try:  # bases ya creadas: añadir la columna del pedido en Markdown
                c.execute("ALTER TABLE tareas ADD COLUMN pedido_md TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            row = c.execute("SELECT sql FROM sqlite_master WHERE name='docs'").fetchone()
            if row is None:
                for tok in ("unicode61 remove_diacritics 2", "unicode61"):
                    try:
                        c.execute("CREATE VIRTUAL TABLE docs USING fts5(titulo, cuerpo, "
                                  f"tarea_id UNINDEXED, tokenize='{tok}')")
                        break
                    except sqlite3.OperationalError:
                        continue
                else:
                    c.execute("CREATE TABLE docs(titulo TEXT, cuerpo TEXT, tarea_id INTEGER)")
                row = c.execute("SELECT sql FROM sqlite_master WHERE name='docs'").fetchone()
            self.fts = "fts5" in (row["sql"] or "").lower()

    @contextmanager
    def _tx(self):
        with self.lock:
            c = sqlite3.connect(self.path, timeout=10)
            c.row_factory = sqlite3.Row
            try:
                yield c
                c.commit()
            finally:
                c.close()

    @staticmethod
    def _clave(cmd: str) -> str:
        return limpiar(" ".join((cmd or "").split()))[:2000]

    @_seguro(None)
    def stat(self, clave: str, delta: float = 1) -> None:
        with self._tx() as c:
            c.execute("INSERT INTO stats VALUES(?,?) ON CONFLICT(clave) DO UPDATE "
                      "SET valor=valor+excluded.valor", (clave, delta))

    # ------------------------------------------------------------ registro estructurado
    @_seguro((None, []))
    def nueva_tarea(self, objetivo: str, pasos: list[str], pedido_md: str = ""):
        with self._tx() as c:
            tid = c.execute("INSERT INTO tareas(titulo,estado,creado,pedido_md) VALUES(?,?,?,?)",
                            (_cut(limpiar(objetivo), 300), "en_curso", time.time(),
                             limpiar(pedido_md)[:4000])).lastrowid
            pids = [c.execute("INSERT INTO pasos(tarea_id,titulo,estado,orden) VALUES(?,?,?,?)",
                              (tid, _cut(limpiar(p), 300), "en_curso", i)).lastrowid
                    for i, p in enumerate(pasos, 1)]
        return tid, pids

    @_seguro(None)
    def paso_estado(self, pid, estado: str) -> None:
        if pid:
            with self._tx() as c:
                c.execute("UPDATE pasos SET estado=? WHERE id=?", (estado, pid))

    @_seguro(None)
    def comando(self, pid, cmd: str, code: int, err: str, timeout: bool,
                objetivo: str, salida_md: str = "") -> None:
        clave = self._clave(cmd)
        with self._tx() as c:
            if pid:
                c.execute("INSERT INTO comandos(paso_id,cmd,salida,estado,resumen,ts) VALUES(?,?,?,?,?,?)",
                          (pid, clave[:500], code, "ok" if code == 0 else "fallo",
                           _cut(limpiar(salida_md), 300), time.time()))
            if es_error_permanente(code, err, timeout):
                lineas = [x.strip() for x in (err or "").splitlines() if x.strip()]
                error = _cut(limpiar(lineas[-1] if lineas else ""), 200)
                c.execute("INSERT INTO fallidos(cmd,error,tarea,veces,ts) VALUES(?,?,?,1,?) "
                          "ON CONFLICT(cmd) DO UPDATE SET veces=veces+1, error=excluded.error, "
                          "ts=excluded.ts, rehabilitado=0",
                          (clave, error, _cut(limpiar(objetivo), 200), time.time()))

    @_seguro(False)
    def es_fallido(self, cmd: str) -> bool:
        with self._tx() as c:
            return c.execute("SELECT 1 FROM fallidos WHERE cmd=? AND rehabilitado=0",
                             (self._clave(cmd),)).fetchone() is not None

    # ------------------------------------------------------------ buscar primero en la bóveda
    def buscar(self, texto: str, k: int = 3) -> list[tuple[str, str]]:
        kw = sorted(tokens(texto), key=len, reverse=True)[:8]
        if not kw:
            return []
        with self._tx() as c:
            if self.fts:
                q = " OR ".join(f'"{w}"' for w in kw)
                rows = c.execute("SELECT titulo,cuerpo FROM docs WHERE docs MATCH ? ORDER BY rank LIMIT ?",
                                 (q, k)).fetchall()
            else:
                cond = " OR ".join("(titulo LIKE ? OR cuerpo LIKE ?)" for _ in kw)
                args = [x for w in kw for x in (f"%{w}%", f"%{w}%")]
                rows = c.execute(f"SELECT titulo,cuerpo FROM docs WHERE {cond} LIMIT ?", (*args, k)).fetchall()
        return [(r["titulo"], r["cuerpo"]) for r in rows]

    @_seguro("")
    def contexto_para(self, objetivo: str, paso: str = "") -> str:
        """Texto corto para añadir al prompt: fallidos relevantes + 2-3 fragmentos."""
        kw = tokens(f"{objetivo} {paso}")
        with self._tx() as c:
            fil = c.execute("SELECT * FROM fallidos WHERE rehabilitado=0 ORDER BY ts DESC LIMIT 80").fetchall()
        punt = sorted(((len(kw & tokens(f["tarea"] + " " + f["cmd"])), f) for f in fil),
                      key=lambda x: -x[0])
        malos = [f for s, f in punt if s > 0][:5]
        lineas = []
        if malos:
            lineas.append("[Bóveda] Comandos que YA fallaron de forma permanente (no repetir):")
            for f in malos:
                sol = f" (solución: {_cut(f['solucion'], 100)})" if f["solucion"] else ""
                lineas.append(f"- `{_cut(f['cmd'], 120)}` -> {_cut(f['error'], 120)}{sol}")
        hallazgos = self.buscar(f"{objetivo} {paso}", 3)
        if hallazgos:
            lineas.append("[Bóveda] Antecedentes de tareas parecidas:")
            for titulo, cuerpo in hallazgos:
                frag = _fragmento(cuerpo, kw)
                lineas.append(f"- {_cut(titulo, 80)}: {frag}")
                self.stat("fragmentos_inyectados")
                self.stat("busqueda_chars_inyectados", len(frag))
                self.stat("busqueda_chars_origen", len(cuerpo))
        self.stat("consultas")
        if not lineas:
            return ""
        return "\n\n<salida_datos>\n" + dato("\n".join(lineas)) + "\n</salida_datos>"

    # ------------------------------------------------------------ cierre y archivador
    @_seguro(None)
    def cerrar_tarea(self, tid, estado_loop: str, t0: float, workdir) -> None:
        if not tid:
            return
        with self._tx() as c:
            c.execute("UPDATE pasos SET estado='fallo' WHERE tarea_id=? AND estado='en_curso'", (tid,))
            malos = c.execute("SELECT COUNT(*) FROM pasos WHERE tarea_id=? AND estado!='ok'", (tid,)).fetchone()[0]
            titulo = c.execute("SELECT titulo FROM tareas WHERE id=?", (tid,)).fetchone()["titulo"]
        estado = "ok" if estado_loop == "ok" and not malos else "fallo"
        proyecto, dudoso = self.detectar_proyecto(titulo, workdir, t0)
        with self._tx() as c:
            c.execute("UPDATE tareas SET estado=?, proyecto=?, proyecto_dudoso=?, cerrado=? WHERE id=?",
                      (estado, proyecto, dudoso, time.time(), tid))
        self._refrescar(tid)

    def detectar_proyecto(self, objetivo: str, workdir, t0: float) -> tuple[str, str]:
        """(proyecto, candidato_dudoso). Orden: repo git -> única subcarpeta tocada -> similitud."""
        kw = tokens(objetivo)
        wd = Path(workdir).expanduser()
        try:  # 1) la carpeta de trabajo es un repo git
            r = subprocess.run(["git", "-C", str(wd), "rev-parse", "--show-toplevel"],
                               capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and Path(r.stdout.strip()).resolve() == wd.resolve():
                return self._fijar(slug(wd.name), kw), ""
        except (OSError, subprocess.SubprocessError):
            pass
        try:  # 2) una sola subcarpeta con archivos modificados en esta tarea
            tocadas = [d for d in wd.iterdir()
                       if d.is_dir() and not d.name.startswith(".") and _tocada(d, t0)]
            if len(tocadas) == 1:
                return self._fijar(slug(tocadas[0].name), kw), ""
        except OSError:
            pass
        with self._tx() as c:  # 3) similitud de palabras con proyectos conocidos
            filas = c.execute("SELECT nombre,palabras FROM proyectos").fetchall()
        mejor, sc = "", 0.0
        for f in filas:
            p = set(f["palabras"].split())
            s = len(kw & p) / len(kw) if kw else 0.0
            if s > sc:
                mejor, sc = f["nombre"], s
        if sc >= 0.5:
            return self._fijar(mejor, kw), ""
        if sc >= 0.25:  # duda: queda por confirmar (POST /boveda/proyecto)
            return "_por_confirmar", mejor
        nuevo = slug("-".join(sorted(kw, key=len, reverse=True)[:3])) if kw else "general"
        return self._fijar(nuevo, kw), ""

    def _fijar(self, nombre: str, kw: set[str]) -> str:
        with self._tx() as c:
            f = c.execute("SELECT palabras FROM proyectos WHERE nombre=?", (nombre,)).fetchone()
            pal = (set(f["palabras"].split()) if f else set()) | kw
            c.execute("INSERT INTO proyectos VALUES(?,?) ON CONFLICT(nombre) DO UPDATE SET palabras=excluded.palabras",
                      (nombre, " ".join(sorted(pal)[:60])))
        return nombre

    def _refrescar(self, tid: int) -> None:
        self._archivar(tid)
        self._indexar(tid)

    def _datos_tarea(self, tid: int):
        with self._tx() as c:
            t = c.execute("SELECT * FROM tareas WHERE id=?", (tid,)).fetchone()
            if not t:
                return None, []
            pasos = []
            for p in c.execute("SELECT * FROM pasos WHERE tarea_id=? ORDER BY orden,id", (tid,)):
                cmds = c.execute("SELECT * FROM comandos WHERE paso_id=? ORDER BY id", (p["id"],)).fetchall()
                pasos.append((p, cmds))
        return t, pasos

    def _indexar(self, tid: int) -> None:
        t, pasos = self._datos_tarea(tid)
        with self._tx() as c:
            c.execute("DELETE FROM docs WHERE tarea_id=?", (tid,))
            if not t:
                return
            lineas = [f"Pedido: {x.strip()}" for x in (t["pedido_md"] or "").splitlines() if x.strip()]
            for p, cmds in pasos:
                lineas.append(f"Paso: {p['titulo']} ({p['estado']})")
                lineas += [f"Comando ok: {x['cmd']}" for x in cmds if x["estado"] == "ok"]
            c.execute("INSERT INTO docs(titulo,cuerpo,tarea_id) VALUES(?,?,?)",
                      (t["titulo"], "\n".join(lineas), tid))

    def _archivar(self, tid: int) -> None:
        t, pasos = self._datos_tarea(tid)
        if not t:
            return
        proyecto = t["proyecto"] or "_por_confirmar"
        carpeta = self.root / "proyectos" / proyecto
        carpeta.mkdir(parents=True, exist_ok=True)
        fecha = datetime.fromtimestamp(t["creado"] or time.time()).strftime("%Y-%m-%d")
        stem = f"{fecha}-{slug(t['titulo'])[:40]}-{tid}"
        rel = f"proyectos/{proyecto}/{stem}.md"
        etiquetas = ["neurotok", f"proyecto/{proyecto}", f"estado/{t['estado']}"]
        etiquetas += sorted(tokens(t["titulo"]), key=len, reverse=True)[:3]
        md = ["---", f"tags: [{', '.join(etiquetas)}]", f"proyecto: {proyecto}", f"estado: {t['estado']}", "---",
              f"# {t['titulo']}", "", f"Proyecto: [[{proyecto}]]"]
        if t["proyecto_dudoso"]:
            md.append(f"> ¿Es del proyecto [[{t['proyecto_dudoso']}]]? Confírmalo con POST /boveda/proyecto.")
        if t["pedido_md"]:
            md += ["", "## Pedido", t["pedido_md"]]
        md += ["", "## Pasos"]
        for i, (p, cmds) in enumerate(pasos, 1):
            md.append(f"{i}. {p['titulo']} - {p['estado']}")
            md += [f"   - `{x['cmd'][:150]}` -> exit {x['salida']}" for x in cmds]
        otros = []
        with self._tx() as c:
            for titulo, _ in self.buscar(t["titulo"], 5):
                f = c.execute("SELECT nota FROM tareas WHERE titulo=? AND id!=? AND nota!=''", (titulo, tid)).fetchone()
                if f:
                    otros.append(Path(f["nota"]).stem)
        if otros:
            md += ["", "## Relacionadas"] + [f"- [[{o}]]" for o in otros[:3]]
        (self.root / rel).write_text("\n".join(md) + "\n", encoding="utf-8")
        anterior = t["nota"]
        with self._tx() as c:
            c.execute("UPDATE tareas SET nota=? WHERE id=?", (rel, tid))
        if anterior and anterior != rel:
            (self.root / anterior).unlink(missing_ok=True)
            self._hub(Path(anterior).parts[1])
        self._hub(proyecto)

    def _hub(self, proyecto: str) -> None:
        carpeta = self.root / "proyectos" / proyecto
        with self._tx() as c:
            filas = c.execute("SELECT titulo,estado,nota FROM tareas WHERE proyecto=? AND nota!='' ORDER BY id",
                              (proyecto if proyecto != "_por_confirmar" else "",)).fetchall()
            if proyecto == "_por_confirmar":
                filas = c.execute("SELECT titulo,estado,nota FROM tareas WHERE proyecto='' AND nota!='' ORDER BY id").fetchall()
        hub = carpeta / f"{proyecto}.md"
        if not filas:
            hub.unlink(missing_ok=True)
            try:
                carpeta.rmdir()
            except OSError:
                pass
            return
        md = ["---", "tags: [neurotok, proyecto]", "---", f"# {proyecto}", ""]
        md += [f"- [[{Path(f['nota']).stem}]] - {_cut(f['titulo'], 80)} ({f['estado']})" for f in filas]
        carpeta.mkdir(parents=True, exist_ok=True)
        hub.write_text("\n".join(md) + "\n", encoding="utf-8")

    # ------------------------------------------------------------ lectura para la app
    @_seguro({"tareas": []})
    def grafo(self, limit: int = 50) -> dict:
        with self._tx() as c:
            out = []
            for t in c.execute("SELECT id,titulo,estado FROM tareas ORDER BY id DESC LIMIT ?", (limit,)).fetchall():
                pasos = []
                for p in c.execute("SELECT id,titulo,estado FROM pasos WHERE tarea_id=? ORDER BY orden,id", (t["id"],)):
                    cmds = [{"id": r["id"], "cmd": r["cmd"], "exit": r["salida"], "estado": r["estado"]}
                            for r in c.execute("SELECT id,cmd,salida,estado FROM comandos WHERE paso_id=? ORDER BY id",
                                               (p["id"],))]
                    pasos.append({**dict(p), "comandos": cmds})
                out.append({**dict(t), "pasos": pasos})
        return {"tareas": out}

    @_seguro([])
    def fallidos_lista(self) -> list:
        with self._tx() as c:
            return [{"id": r["id"], "cmd": r["cmd"], "error": r["error"], "tarea": r["tarea"],
                     "veces": r["veces"], "solucion": r["solucion"], "rehabilitado": bool(r["rehabilitado"])}
                    for r in c.execute("SELECT * FROM fallidos ORDER BY ts DESC").fetchall()]

    @_seguro({})
    def metricas(self) -> dict:
        with self._tx() as c:
            st = {r["clave"]: r["valor"] for r in c.execute("SELECT clave,valor FROM stats")}
            nt = c.execute("SELECT COUNT(*) FROM tareas").fetchone()[0]
            nf = c.execute("SELECT COUNT(*) FROM fallidos WHERE rehabilitado=0").fetchone()[0]
        orig, inj = st.get("busqueda_chars_origen", 0), st.get("busqueda_chars_inyectados", 0)
        return {"consultas_boveda": int(st.get("consultas", 0)),
                "fragmentos_inyectados": int(st.get("fragmentos_inyectados", 0)),
                # frente a pegar enteras las notas de las que salió cada fragmento
                "ahorro_busqueda_pct": round((1 - inj / orig) * 100, 1) if orig and inj < orig else 0.0,
                "rechazos_repetidos": int(st.get("rechazos_repetidos", 0)),
                "tareas_total": nt, "fallidos_activos": nf, "busqueda_fts5": self.fts}

    # ------------------------------------------------------------ editar / borrar / rehabilitar
    def accion(self, nombre: str, d: dict) -> tuple[bool, str]:
        try:
            if nombre == "editar":
                return self.editar(str(d.get("tipo", "")), int(d["id"]), d)
            if nombre == "borrar":
                return self.borrar(str(d.get("tipo", "")), int(d["id"]))
            if nombre == "rehabilitar":
                return self.rehabilitar(int(d["id"]), bool(d.get("valor", True)))
            if nombre == "proyecto":
                return self.asignar_proyecto(int(d["id"]), str(d.get("proyecto", "")))
            return False, "acción desconocida"
        except (KeyError, ValueError, TypeError):
            return False, "datos inválidos"
        except sqlite3.Error:
            return False, "error de base de datos"

    def _tarea_de(self, c, tipo: str, id_: int):
        if tipo == "tarea":
            return id_
        if tipo == "paso":
            r = c.execute("SELECT tarea_id FROM pasos WHERE id=?", (id_,)).fetchone()
        elif tipo == "comando":
            r = c.execute("SELECT p.tarea_id FROM comandos x JOIN pasos p ON p.id=x.paso_id WHERE x.id=?",
                          (id_,)).fetchone()
        else:
            return None
        return r[0] if r else None

    def editar(self, tipo: str, id_: int, d: dict) -> tuple[bool, str]:
        if tipo not in TABLAS:
            return False, "tipo inválido"
        campos = {k: _cut(limpiar(str(d[k])), 500) for k in EDITABLES[tipo] if k in d}
        if not campos:
            return False, "nada que editar"
        with self._tx() as c:
            sets = ", ".join(f"{k}=?" for k in campos)
            n = c.execute(f"UPDATE {TABLAS[tipo]} SET {sets} WHERE id=?", (*campos.values(), id_)).rowcount
            tid = self._tarea_de(c, tipo, id_)
        if not n:
            return False, "no existe"
        if tid:
            self._refrescar(tid)
        return True, ""

    def borrar(self, tipo: str, id_: int) -> tuple[bool, str]:
        if tipo not in TABLAS:
            return False, "tipo inválido"
        nota = proyecto = ""
        with self._tx() as c:
            tid = self._tarea_de(c, tipo, id_)
            if tipo == "tarea":
                t = c.execute("SELECT nota,proyecto FROM tareas WHERE id=?", (id_,)).fetchone()
                if not t:
                    return False, "no existe"
                nota, proyecto = t["nota"], t["proyecto"] or "_por_confirmar"
                c.execute("DELETE FROM comandos WHERE paso_id IN (SELECT id FROM pasos WHERE tarea_id=?)", (id_,))
                c.execute("DELETE FROM pasos WHERE tarea_id=?", (id_,))
                c.execute("DELETE FROM docs WHERE tarea_id=?", (id_,))
                c.execute("DELETE FROM tareas WHERE id=?", (id_,))
            else:
                if tipo == "paso":
                    c.execute("DELETE FROM comandos WHERE paso_id=?", (id_,))
                n = c.execute(f"DELETE FROM {TABLAS[tipo]} WHERE id=?", (id_,)).rowcount
                if not n:
                    return False, "no existe"
        if nota:
            (self.root / nota).unlink(missing_ok=True)
            self._hub(proyecto)
        elif tid:
            self._refrescar(tid)
        return True, ""

    def rehabilitar(self, id_: int, valor: bool = True) -> tuple[bool, str]:
        with self._tx() as c:
            n = c.execute("UPDATE fallidos SET rehabilitado=? WHERE id=?", (1 if valor else 0, id_)).rowcount
        return (True, "") if n else (False, "no existe")

    def asignar_proyecto(self, tid: int, proyecto: str) -> tuple[bool, str]:
        nombre = slug(proyecto)
        t, _ = self._datos_tarea(tid)
        if not t or not proyecto.strip():
            return False, "no existe o proyecto vacío"
        self._fijar(nombre, tokens(t["titulo"]))
        with self._tx() as c:
            c.execute("UPDATE tareas SET proyecto=?, proyecto_dudoso='' WHERE id=?", (nombre, tid))
        self._refrescar(tid)
        return True, ""


if __name__ == "__main__":  # prueba rápida: python backend/boveda_db.py
    import tempfile
    d = BovedaDB(tempfile.mkdtemp())
    tid, pids = d.nueva_tarea("Crear una API de turnos con Express", ["Instalar express", "Crear servidor"])
    d.comando(pids[0], "npm i expres", 127, "bash: expres: command not found", False, "Crear API turnos")
    d.comando(pids[0], "curl https://x.io", 6, "curl: Could not resolve host", False, "Crear API turnos")
    d.comando(pids[0], "npm i express", 0, "", False, "Crear API turnos", "ok")
    assert d.es_fallido("npm   i  expres") and not d.es_fallido("curl https://x.io")
    assert not d.es_fallido("npm i express")
    d.paso_estado(pids[0], "ok")
    d.cerrar_tarea(tid, "ok", time.time() - 5, tempfile.mkdtemp())
    g = d.grafo()["tareas"][0]
    assert g["estado"] == "fallo" and g["pasos"][1]["estado"] == "fallo" and len(g["pasos"][0]["comandos"]) == 3
    ctx = d.contexto_para("API de turnos con Express", "Instalar express")
    assert "expres" in ctx and "Antecedentes" in ctx, ctx
    f = d.fallidos_lista()[0]
    assert d.rehabilitar(f["id"]) == (True, "") and not d.es_fallido("npm i expres")
    assert d.editar("fallido", f["id"], {"solucion": "es express"})[0]
    assert d.borrar("tarea", tid) == (True, "") and not d.grafo()["tareas"]
    print("OK", d.metricas(), "FTS5" if d.fts else "sin FTS5")
