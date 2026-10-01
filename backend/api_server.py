"""api_server.py - API REST para el Dashboard de Neurotok (solo librería estándar, sin FastAPI).
Escucha en http://127.0.0.1:8000"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agent_loop import RUNTIME, AgentLoop
from vault_manager import VaultManager
from worker_pool import WorkerPool

pool = WorkerPool("cuentas.json")
vault = VaultManager()
loop = AgentLoop(pool, vault)
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
    "/boveda": lambda: {"estado_actual_md": vault.read_context(), "metricas": vault.metrics()},
    "/flow": RUNTIME.flow,
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, {})

    def do_GET(self) -> None:  # noqa: N802
        fn = ROUTES_GET.get(self.path.split("?")[0])
        self._send(200, fn()) if fn else self._send(404, {"error": "no existe"})

    def do_POST(self) -> None:  # noqa: N802
        global _thread
        path = self.path.split("?")[0]
        if path == "/run":
            try:
                n = int(self.headers.get("Content-Length", 0))
                objetivo = json.loads(self.rfile.read(n) or b"{}").get("objetivo", "").strip()
            except (ValueError, json.JSONDecodeError):
                return self._send(400, {"error": "JSON inválido"})
            if not objetivo:
                return self._send(400, {"error": "falta 'objetivo'"})
            if _thread and _thread.is_alive():
                return self._send(409, {"error": "Ya hay una ejecución en curso"})
            _thread = threading.Thread(target=loop.run, args=(objetivo,), daemon=True)
            _thread.start()
            return self._send(200, {"ok": True})
        if path == "/stop":
            loop.stop()
            return self._send(200, {"ok": True})
        self._send(404, {"error": "no existe"})

    def log_message(self, *args) -> None:  # silencio
        pass


if __name__ == "__main__":
    print("Neurotok API en http://127.0.0.1:8000  (Ctrl+C para salir)")
    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
