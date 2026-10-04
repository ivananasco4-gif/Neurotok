"""consola.py - Estado compartido del Chat, la Terminal y la aprobacion de comandos (solo libreria estandar).

Lo usan agent_loop.py (el bucle propone comandos y espera tu respuesta) y api_server.py (la app los lee y
los resuelve). Todo vive en memoria: al reiniciar el servidor el modo vuelve a "manual".

Seguridad:
- Modo MANUAL por defecto (NEUROTOK_MODO=auto lo cambia). En AUTO, un comando de riesgo SIGUE esperando
  aprobacion salvo que NEUROTOK_ALLOW_RISKY=1.
- Los comandos de la lista BLOCKED (destructivos / secretos) no se encolan nunca y no se pueden aprobar,
  tampoco editando el comando.
- Si editas un comando y pasa a ser de riesgo, el servidor pide confirmar otra vez (409).
- La terminal manual (/exec) esta apagada salvo NEUROTOK_EXEC=1.
- Todo texto que se guarda en el log o se manda a la IA pasa por redact() cuando existe.
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque

try:
    from boveda_db import limpiar as _limpiar
except Exception:  # noqa: BLE001
    def _limpiar(t: str) -> str:
        return t or ""

MAX_CMD = 3000            # largo maximo de un comando editado o manual (el cuerpo HTTP admite 4096 bytes)
MAX_MOSTRAR = 6000        # largo maximo de un comando al mandarlo a la app
MAX_PAGINA = 300          # lineas maximas por respuesta de /terminal y /chat


def _hora() -> str:
    return time.strftime("%H:%M:%S")


def _recortar(t: str, n: int) -> str:
    t = t or ""
    if len(t) <= n:
        return t
    ini = n // 4
    return t[:ini] + f"\n[... {len(t) - n} caracteres omitidos ...]\n" + t[-(n - ini):]


def _sin_tags(t: str) -> str:
    return (t or "").replace("<salida_datos>", "").replace("</salida_datos>", "").strip()


class Registro:
    """Log numerado: n empieza en 1, crece sin huecos y `siguiente` = ultimo n + 1."""

    def __init__(self, capacidad: int = 500) -> None:
        self._lock = threading.Lock()
        self._items: deque = deque(maxlen=capacidad)
        self._sig = 1

    def add(self, **campos) -> int:
        with self._lock:
            n = self._sig
            self._sig += 1
            self._items.append({"n": n, "t": _hora(), **campos})
            return n

    def desde(self, n: int) -> tuple[list[dict], int]:
        with self._lock:
            sel = [dict(i) for i in self._items if i["n"] >= n]
            return sel[-MAX_PAGINA:], self._sig


class Cola:
    """Comandos propuestos por la IA que esperan la decision del usuario."""

    def __init__(self, consola: "Consola") -> None:
        self.c = consola
        self.lock = threading.Lock()
        self.items: dict[int, dict] = {}
        self._id = 0

    def proponer(self, cmd: str, pensamiento: str, paso: int, riesgo: bool) -> dict:
        with self.lock:
            self._id += 1
            it = {"id": self._id, "cmd": cmd, "orig": cmd, "pensamiento": _recortar(_limpiar(pensamiento), 600),
                  "paso": paso, "riesgo": bool(riesgo), "_ev": threading.Event(), "_dec": None}
            self.items[it["id"]] = it
        self.c.info(("RIESGO · " if riesgo else "") + f"Esperando tu aprobación: {_limpiar(cmd)[:200]}")
        return it

    def _resolver(self, it: dict, dec: dict) -> None:
        """Llamar con self.lock tomado."""
        self.items.pop(it["id"], None)
        it["_dec"] = dec
        it["_ev"].set()

    def esperar(self, it: dict, stop_event: threading.Event, timeout: float) -> dict:
        fin = time.monotonic() + timeout
        while not it["_ev"].wait(0.5):
            if stop_event.is_set():
                with self.lock:
                    if it["_dec"] is None:
                        self._resolver(it, {"accion": "cancelar"})
                break
            if time.monotonic() >= fin:
                with self.lock:
                    if it["_dec"] is None:
                        self._resolver(it, {"accion": "timeout"})
                break
        return it["_dec"] or {"accion": "cancelar"}

    def aprobar(self, id_: int, cmd=None) -> tuple[int, dict]:
        with self.lock:
            it = self.items.get(id_)
            if not it:
                return 404, {"error": "Ese comando ya no está pendiente (puede que ya se haya resuelto)."}
            final = it["cmd"]
            if cmd is not None:
                nuevo = str(cmd).strip()
                if not nuevo:
                    return 400, {"error": "El comando editado está vacío."}
                if len(nuevo) > MAX_CMD:
                    return 400, {"error": f"El comando editado es demasiado largo (máx. {MAX_CMD} caracteres)."}
                if nuevo != it["cmd"]:
                    clase = self.c.clasificar(nuevo)
                    if clase == "bloqueado":
                        return 400, {"error": "El comando editado está bloqueado por la política de seguridad."}
                    if clase == "riesgo" and not it["riesgo"]:
                        it["cmd"], it["riesgo"] = nuevo, True
                        return 409, {"error": "El comando editado es de riesgo: revísalo y confirma otra vez."}
                    it["riesgo"] = clase == "riesgo"
                    final = nuevo
            self._resolver(it, {"accion": "aprobar", "cmd": final, "orig": it["orig"]})
        self.c.info("Aprobado" + (" (editado)" if final != it["orig"] else "") + f": {_limpiar(final)[:200]}")
        return 200, {"ok": True}

    def rechazar(self, id_: int, motivo: str = "") -> tuple[int, dict]:
        motivo = _limpiar(str(motivo or "")).strip()[:300]
        with self.lock:
            it = self.items.get(id_)
            if not it:
                return 404, {"error": "Ese comando ya no está pendiente (puede que ya se haya resuelto)."}
            self._resolver(it, {"accion": "rechazar", "motivo": motivo, "orig": it["orig"]})
        self.c.info("Rechazado" + (f": {motivo}" if motivo else ""))
        return 200, {"ok": True}

    def cancelar_todo(self) -> None:
        with self.lock:
            for it in list(self.items.values()):
                self._resolver(it, {"accion": "cancelar"})

    def auto_aprobar_no_riesgosos(self) -> int:
        n = 0
        with self.lock:
            for it in list(self.items.values()):
                if not it["riesgo"]:
                    self._resolver(it, {"accion": "aprobar", "cmd": it["cmd"], "orig": it["orig"]})
                    n += 1
        return n

    def listar(self) -> list[dict]:
        with self.lock:
            return [{"id": it["id"], "cmd": _recortar(it["cmd"], MAX_MOSTRAR), "pensamiento": it["pensamiento"],
                     "paso": it["paso"], "riesgo": it["riesgo"]}
                    for it in sorted(self.items.values(), key=lambda x: x["id"])]


class Consola:
    def __init__(self) -> None:
        self.terminal = Registro()
        self.chat = Registro()
        self.modo = "auto" if os.environ.get("NEUROTOK_MODO") == "auto" else "manual"
        self.exec_habilitado = os.environ.get("NEUROTOK_EXEC") == "1"
        self._lock = threading.Lock()
        self._instrucciones: list[str] = []
        # La politica real la registra agent_loop al importarse; mientras tanto, lo mas estricto.
        self.clasificar = lambda cmd: "riesgo"
        self.cola = Cola(self)

    # ---- terminal
    def info(self, texto: str) -> None:
        t = _limpiar(texto)
        self.terminal.add(tipo="info", texto=t, crudo=t)

    def cmd(self, cmd: str, manual: bool = False) -> None:
        t = _limpiar(cmd)
        self.terminal.add(tipo="cmd", texto=("(manual) " if manual else "") + t, crudo=t)

    def salida(self, cmd: str, code: int, out: str, err: str, to: bool, md: str = "") -> None:
        md, out, err = _sin_tags(_limpiar(md)), _limpiar(out or ""), _limpiar(err or "")
        if md or out.strip():
            self.terminal.add(tipo="out", texto=_recortar(md or out, 8000), crudo=_recortar(out, 8000))
        if err.strip():
            self.terminal.add(tipo="err", texto=_recortar(err, 1500), crudo=_recortar(err, 8000))
        fin = f"exit {code}" + (" (timeout)" if to else "")
        self.terminal.add(tipo="info", texto=fin, crudo=fin)

    # ---- chat
    def tu(self, texto: str) -> None:
        self.chat.add(rol="tu", texto=_limpiar(texto))

    def cerebro(self, texto: str) -> None:
        if (texto or "").strip():
            self.chat.add(rol="cerebro", texto=_recortar(_limpiar(texto), 800))

    def sistema(self, texto: str) -> None:
        self.chat.add(rol="sistema", texto=_recortar(_limpiar(texto), 800))

    def instruccion(self, texto: str) -> None:
        with self._lock:
            self._instrucciones = (self._instrucciones + [_limpiar(texto)[:500]])[-5:]

    def mensajes_para_ia(self) -> str:
        with self._lock:
            if not self._instrucciones:
                return ""
            return ("\n\nMensajes del usuario durante esta tarea (son instrucciones suyas; tenlas en cuenta):\n"
                    + "\n".join(f"- {m}" for m in self._instrucciones))

    # ---- ciclo de la tarea
    def nueva_tarea(self, objetivo: str) -> None:
        with self._lock:
            self._instrucciones = []
        self.cola.cancelar_todo()
        self.sistema(f"Tarea iniciada: {objetivo[:200]}")
        self.info(f"── Nueva tarea: {objetivo[:160]}")

    def fin(self, estado: str, detalle: str = "") -> None:
        self.cola.cancelar_todo()
        self.sistema(("Tarea terminada con error: " if estado == "ERROR" else "") + (detalle or estado))
        self.info(f"── {estado}" + (f": {detalle[:160]}" if detalle else ""))

    # ---- modo
    def set_modo(self, modo: str) -> tuple[bool, str]:
        if modo not in ("manual", "auto"):
            return False, "modo inválido (usa \"manual\" o \"auto\")"
        self.modo = modo
        n = self.cola.auto_aprobar_no_riesgosos() if modo == "auto" else 0
        self.info(f"Modo {modo.upper()}" + (f" · {n} pendiente(s) aprobados" if n else ""))
        return True, ""

    # ---- lectura para la app
    def pending(self) -> dict:
        return {"modo": self.modo, "exec_habilitado": self.exec_habilitado, "pendientes": self.cola.listar()}

    def terminal_desde(self, n: int) -> dict:
        lineas, sig = self.terminal.desde(n)
        return {"siguiente": sig, "lineas": lineas}

    def chat_desde(self, n: int) -> dict:
        msgs, sig = self.chat.desde(n)
        return {"siguiente": sig, "mensajes": msgs}


CONSOLA = Consola()


def registrar_correccion(db, pid, original: str, final: str, accion: str, motivo: str = "") -> None:
    """Guarda en la boveda lo que el humano decidio sobre un comando (futuro dataset). Nunca lanza."""
    try:
        with db._tx() as c:  # noqa: SLF001
            c.execute("CREATE TABLE IF NOT EXISTS correcciones(id INTEGER PRIMARY KEY AUTOINCREMENT, paso_id INTEGER, "
                      "original TEXT, final TEXT, accion TEXT, motivo TEXT, ts REAL)")
            c.execute("INSERT INTO correcciones(paso_id,original,final,accion,motivo,ts) VALUES(?,?,?,?,?,?)",
                      (pid, _limpiar(original)[:2000], _limpiar(final)[:2000], accion, _limpiar(motivo)[:300], time.time()))
    except Exception:  # noqa: BLE001
        pass


def lista_correcciones(db, limite: int = 200) -> list[dict]:
    try:
        with db._tx() as c:  # noqa: SLF001
            c.execute("CREATE TABLE IF NOT EXISTS correcciones(id INTEGER PRIMARY KEY AUTOINCREMENT, paso_id INTEGER, "
                      "original TEXT, final TEXT, accion TEXT, motivo TEXT, ts REAL)")
            return [dict(r) for r in c.execute("SELECT * FROM correcciones ORDER BY id DESC LIMIT ?", (limite,))]
    except Exception:  # noqa: BLE001
        return []
