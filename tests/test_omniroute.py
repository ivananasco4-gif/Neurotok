"""Tests offline: servidor OmniRoute falso (http.server). Ejecutar: python3 tests/test_omniroute.py"""
import json, os, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from errores_llm import clasificar_error as ce
from omniroute import PoolOmniRoute, listar_modelos

MODELOS = ["ok-a", "ok-b", "ritmo", "cuota", "gone", "text-embedding-3", "whisper-1", "ok-a"]


def falso(clave):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _send(self, code, obj, extra=None):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            for k, v in (extra or {}).items(): self.send_header(k, v)
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def do_GET(self):
            if self.headers.get("Authorization") != "Bearer " + clave:
                return self._send(401, {"error": {"message": "invalid api key"}})
            self._send(200, {"object": "list", "data": [{"id": m} for m in MODELOS]})
        def do_POST(self):
            if self.headers.get("Authorization") != "Bearer " + clave:
                return self._send(401, {"error": {"message": "invalid api key"}})
            m = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["model"]
            if m == "ritmo":
                return self._send(429, {"error": {"code": "rate_limit_exceeded", "message": "slow"}}, {"Retry-After": "2"})
            if m == "cuota":
                return self._send(429, {"error": {"code": "insufficient_quota", "message": "You exceeded your current quota"}})
            if m == "gone":
                return self._send(404, {"error": {"code": "model_not_found", "message": "model does not exist"}})
            self._send(200, {"choices": [{"message": {"content": "hola desde " + m}}]})
    s = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


class Reloj:
    t = 1000.0
    def __call__(self): return self.t


def test_clasificador():
    assert ce(429, {"Retry-After": "3"}, {"error": {"code": "rate_limit_exceeded"}}) == ("ritmo", 3)
    assert ce(429, {}, {"error": {"code": "insufficient_quota"}})[0] == "cuota"
    g = {"error": {"status": "RESOURCE_EXHAUSTED", "details": [{"@type": "x.RetryInfo", "retryDelay": "34s"}]}}
    assert ce(429, {}, g, "gemini") == ("ritmo", 34)
    gd = {"error": {"status": "RESOURCE_EXHAUSTED", "details": [{"@type": "x.QuotaFailure",
          "violations": [{"quotaId": "RequestsPerDayPerProject"}]}, {"@type": "x.RetryInfo", "retryDelay": "20s"}]}}
    t, s = ce(429, {}, gd, "gemini"); assert t == "cuota" and s >= 3600
    assert ce(401, {}, "no")[0] == "auth" and ce(None)[0] == "red" and ce(503)[0] == "red"
    assert ce(404, {}, {"error": {"code": "model_not_found"}})[0] == "modelo"
    assert ce(429, {"retry-after": "3600"}, "")[0] == "cuota"
    for x in (ce(429, None, None), ce(500, {}, b"\xff"), ce(429, {"retry-after": "zzz"}, "{")):
        assert x[0] in ("ritmo", "otro") and x[1] > 0


def test_pool_rota():
    a, b = falso("ka"), falso("kb")
    ua = "http://127.0.0.1:%d/v1" % a.server_port
    ub = "http://127.0.0.1:%d/v1" % b.server_port
    ids = listar_modelos(ua, "ka"); assert ids == ["ok-a", "ok-b", "ritmo", "cuota", "gone"], ids
    clk = Reloj()
    cuentas = [{"id": "A", "proveedor": "omniroute", "url": ua, "credencial": "ka", "modelos": "auto", "max_modelos": 100},
               {"id": "B", "proveedor": "omniroute", "url": ub, "credencial": "kb", "modelos": ["ok-a"]},
               {"id": "gem", "proveedor": "gemini"}]
    p = PoolOmniRoute(cuentas, reloj=clk)
    assert len(p.n) == 6                                  # 5 + 1; la cuenta gemini se ignora
    # fuerza que primero toque 'ritmo', luego 'cuota', 'gone', y al final responda una OK
    for k in p.n.values(): k["usos"] = 5
    for nid in ("A/ritmo", "A/cuota", "A/gone"): p.n[nid]["usos"] = 0
    txt, nid = p.ejecutar([{"role": "user", "content": "hi"}])
    assert txt and txt.startswith("hola"), (txt, nid)
    s = {x["id"]: x for x in p.snapshot()}
    assert s["A/ritmo"]["cooldown_s"] == 2 and s["A/ritmo"]["estado"] == "en_pausa"
    assert s["A/cuota"]["cooldown_s"] >= 3600
    assert s["A/gone"]["cooldown_s"] >= 600
    assert s["A/ok-a"]["estado"] == "libre"              # un modelo en pausa no pausa la instancia
    clk.t += 3                                           # pasa el ritmo
    assert {x["id"]: x for x in p.snapshot()}["A/ritmo"]["estado"] == "libre"
    # instancia caída -> pausa de instancia, B sigue sirviendo
    a.shutdown(); a.server_close()
    for k in p.n.values(): k["usos"] = 9
    p.n["A/ok-a"]["usos"] = 0
    txt, nid = p.ejecutar([{"role": "user", "content": "hi"}])
    assert nid.startswith("B/"), nid
    r = {i["id"]: i for i in p.resumen()["instancias"]}
    assert r["A"]["disponibles"] == 0 and r["A"]["en_pausa"] == 5 and r["B"]["disponibles"] == 1
    assert "red" in (r["A"]["ultimo_error"] or "")
    # todo agotado -> (None, error), sin colgarse
    p.cooldown("B/ok-a", 60); assert p.ejecutar([{"role": "user", "content": "x"}])[0] is None
    # reparto equilibrado
    q = PoolOmniRoute([cuentas[1]], reloj=clk); n1 = q.acquire(); q.release(n1["id"]); n2 = q.acquire()
    assert n1["id"] and n2["usos"] == 2
    b.shutdown()


if __name__ == "__main__":
    test_clasificador(); test_pool_rota(); print("OK: todos los tests pasan")
