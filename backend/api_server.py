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

from agent_loop import RUNTIME, AgentLoop
from boveda_db import BovedaDB
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
        fn = ROUTES_GET.get(self.path.split("?")[0])
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
            _thread = threading.Thread(target=loop.run, args=(objetivo,), daemon=True)
            _thread.start()
            return self._send(200, {"ok": True})
        if path == "/stop":
            loop.stop()
            return self._send(200, {"ok": True})
        if path.startswith("/boveda/"):
            return self._boveda_post(path[len("/boveda/"):])
        self._send(404, {"error": "no existe"})

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
