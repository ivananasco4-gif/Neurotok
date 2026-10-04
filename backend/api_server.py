"""api_server.py - API REST de Neurotok (solo librería estándar).
Seguridad: solo 127.0.0.1, token obligatorio (Authorization: Bearer ...), sin CORS."""
from __future__ import annotations

import hmac
import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from agent_loop import RUNTIME, AgentLoop
from boveda_db import BovedaDB
from consola import CONSOLA, MAX_CMD, lista_correcciones
from vault_manager import VaultManager
from worker_pool import WorkerPool

TOKEN_FILE = Path(os.environ.get("NEUROTOK_TOKEN_FILE", "~/.neurotok_token")).expanduser()
HOSTS_OK = {"127.0.0.1:8000", "localhost:8000", "127.0.0.1", "localhost"}
MAX_BODY = 4096
MAX_GOAL = 2000


def load_token() -> str:
    if TOKEN_FILE.exists():
        t = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if len(t) >= 32:
            return t
    t = secrets.token_urlsafe(32)
    TOKEN_FILE.write_text(t, encoding="utf-8")
    os.chmod(TOKEN_FILE, 0o600)
    return t


TOKEN = load_token()
pool = WorkerPool("cuentas.json")
vault = VaultManager()
db = BovedaDB(vault.root)
loop = AgentLoop(pool, vault, db)
_thread: threading.Thread | None = None
_run_lock = threading.Lock()

SUBCEREBROS = {"orquestador": "Cerebro Central (Router)", "arquitecto": "Sub-Cerebro Arquitecto",
               "creador": "Sub-Cerebro Creador / Code", "auditor": "Sub-Cerebro Auditor / Debugger"}


def get_neurons() -> dict:
    lista = pool.snapshot()
    for n in lista:
        n["sub_cerebro"] = SUBCEREBROS.get(n["rol"], n["rol"])
    return {"neuronas": lista, "sub_cerebros": SUBCEREBROS}


ROUTES_GET = {
    "/status": RUNTIME.status,
    "/neurons": get_neurons,
    "/boveda": lambda: {"estado_actual_md": vault.read_context(), "metricas": {**vault.metrics(), **db.metricas()}},
    "/boveda/grafo": db.grafo,
    "/boveda/fallidos": db.fallidos_lista,
    "/flow": RUNTIME.flow,
    "/pending": CONSOLA.pending,
    "/correcciones": lambda: lista_correcciones(db),
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _guard(self) -> bool:
        """True si el pedido es válido; si no, ya respondió el error."""
        if self.headers.get("Host", "") not in HOSTS_OK:
            self._send(403, {"error": "host no permitido"})
            return False
        h = self.headers.get("Authorization", "")
        if not (h.startswith("Bearer ") and hmac.compare_digest(h[7:].strip(), TOKEN)):
            self._send(401, {"error": "token inválido"})
            return False
        return True

    def do_GET(self) -> None:  # noqa: N802
        if not self._guard():
            return
        ruta, _, qs = self.path.partition("?")
        if ruta in ("/terminal", "/chat"):
            try:
                desde = int(parse_qs(qs).get("desde", ["0"])[0])
            except ValueError:
                desde = 0
            return self._send(200, CONSOLA.terminal_desde(desde) if ruta == "/terminal" else CONSOLA.chat_desde(desde))
        fn = ROUTES_GET.get(ruta)
        self._send(200, fn()) if fn else self._send(404, {"error": "no existe"})

    def do_POST(self) -> None:  # noqa: N802
        global _thread
        if not self._guard():
            return
        path = self.path.split("?")[0]
        if path == "/run":
            try:
                n = int(self.headers.get("Content-Length", 0))
                if n > MAX_BODY:
                    return self._send(413, {"error": "pedido demasiado grande"})
                objetivo = str(json.loads(self.rfile.read(n) or b"{}").get("objetivo", "")).strip()
            except (ValueError, json.JSONDecodeError):
                return self._send(400, {"error": "JSON inválido"})
            if not objetivo or len(objetivo) > MAX_GOAL:
                return self._send(400, {"error": "objetivo vacío o demasiado largo"})
            if _thread and _thread.is_alive():
                return self._send(409, {"error": "Ya hay una ejecución en curso"})
            CONSOLA.tu(objetivo)
            _thread = threading.Thread(target=loop.run, args=(objetivo,), daemon=True)
            _thread.start()
            return self._send(200, {"ok": True})
        if path == "/stop":
            loop.stop()
            return self._send(200, {"ok": True})
        if path in ("/approve", "/reject", "/modo", "/exec", "/chat"):
            return self._consola_post(path)
        if path.startswith("/boveda/"):
            return self._boveda_post(path[len("/boveda/"):])
        self._send(404, {"error": "no existe"})

    def _consola_post(self, path: str) -> None:
        global _thread
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > MAX_BODY:
                return self._send(413, {"error": "pedido demasiado grande"})
            d = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(d, dict):
                raise ValueError
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"error": "JSON inválido"})
        if path in ("/approve", "/reject"):
            try:
                id_ = int(d["id"])
            except (KeyError, TypeError, ValueError):
                return self._send(400, {"error": "falta el id del comando"})
            if path == "/approve":
                code, resp = CONSOLA.cola.aprobar(id_, d.get("cmd"))
            else:
                code, resp = CONSOLA.cola.rechazar(id_, d.get("motivo", ""))
            return self._send(code, resp)
        if path == "/modo":
            ok, msg = CONSOLA.set_modo(str(d.get("modo", "")))
            return self._send(200, {"ok": True, "modo": CONSOLA.modo}) if ok else self._send(400, {"error": msg})
        if path == "/exec":
            if not CONSOLA.exec_habilitado:
                return self._send(403, {"error": "La terminal manual está desactivada. "
                                                 "Arranca el servidor con NEUROTOK_EXEC=1 para usarla."})
            cmd = str(d.get("cmd", "")).strip()
            if not cmd or len(cmd) > MAX_CMD:
                return self._send(400, {"error": f"comando vacío o demasiado largo (máx. {MAX_CMD})"})
            clase = CONSOLA.clasificar(cmd)
            if clase == "bloqueado":
                CONSOLA.info("Comando manual bloqueado por la política de seguridad")
                return self._send(403, {"error": "Comando bloqueado por la política de seguridad."})
            if clase == "riesgo" and os.environ.get("NEUROTOK_ALLOW_RISKY") != "1":
                return self._send(403, {"error": "Comando de riesgo: la terminal manual no lo ejecuta. Pídeselo al "
                                                 "cerebro y apruébalo en la cola, o arranca con NEUROTOK_ALLOW_RISKY=1."})
            ok, msg = loop.exec_manual(cmd)
            return self._send(200, {"ok": True}) if ok else self._send(409, {"error": msg})
        texto = str(d.get("texto", "")).strip()  # POST /chat
        if not texto or len(texto) > MAX_GOAL:
            return self._send(400, {"error": "mensaje vacío o demasiado largo"})
        with _run_lock:
            en_curso = _thread is not None and _thread.is_alive()
            CONSOLA.tu(texto)
            if en_curso:  # mensaje durante una tarea: instruccion para el cerebro
                CONSOLA.instruccion(texto)
                CONSOLA.sistema("Mensaje recibido: el cerebro lo tendrá en cuenta en su próximo turno.")
                return self._send(200, {"ok": True, "tipo": "mensaje"})
            _thread = threading.Thread(target=loop.run, args=(texto,), daemon=True)  # sin tarea: es un objetivo nuevo
            _thread.start()
        return self._send(200, {"ok": True, "tipo": "tarea"})

    def _boveda_post(self, accion: str) -> None:
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > MAX_BODY:
                return self._send(413, {"error": "pedido demasiado grande"})
            datos = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(datos, dict):
                raise ValueError
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"error": "JSON inválido"})
        ok, msg = db.accion(accion, datos)
        self._send(200, {"ok": True}) if ok else self._send(400, {"ok": False, "error": msg})

    def log_message(self, *args) -> None:
        pass


if __name__ == "__main__":
    print("Neurotok API en http://127.0.0.1:8000")
    print(f"Token para la app:  cat {TOKEN_FILE}")
    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
