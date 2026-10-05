"""Integración WorkerPool + OmniRoute falso. Offline. Ejecutar desde la raíz: python3 tests/test_pool_omniroute.py"""
import json, os, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.dirname(__file__))
import worker_pool as wp
from test_omniroute import falso


def siempre429():
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _s(self, c, o, h=None):
            b = json.dumps(o).encode(); self.send_response(c)
            for k, v in (h or {}).items(): self.send_header(k, v)
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def do_GET(self): self._s(200, {"data": [{"id": "m%d" % i} for i in range(10)]})
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self._s(429, {"error": {"code": "rate_limit_exceeded"}}, {"Retry-After": "5"})
    s = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=s.serve_forever, daemon=True).start(); return s


def agente(pool, intentos=12):
    """Imita el bucle: acquire -> call_llm -> cooldown según excepción -> release."""
    for _ in range(intentos):
        n = pool.acquire(["creador"])
        if not n: return None, None
        try:
            return wp.call_llm(n, "sys", "hola"), n
        except wp.RateLimitError as e: pool.cooldown(n, e.retry_after, str(e))
        except wp.AuthError as e: pool.cooldown(n, 3600, str(e))
        except wp.ModelError as e: pool.cooldown(n, 600, str(e))
        except wp.LLMError as e: pool.cooldown(n, 60, str(e))
        finally: pool.release(n)
    return None, None


def test_todo():
    a, b, c = falso("ka"), falso("kb"), siempre429()
    u = lambda s: "http://127.0.0.1:%d/v1" % s.server_port
    cuentas = {"cuentas": [
        {"id": "sim", "proveedor": "simulado", "credencial": "x", "rol_sugerido": "orquestador"},
        {"id": "plantilla", "proveedor": "groq", "credencial": "TU_API_KEY_GROQ"},
        {"id": "A", "proveedor": "omniroute", "credencial": "ka", "url": u(a), "modelos": "auto", "max_modelos": 3},
        {"id": "B", "proveedor": "omniroute", "credencial": "kb", "url": u(b), "modelos": ["ok-a"]},
        {"id": "C", "proveedor": "omniroute", "credencial": "", "url": u(c), "modelos": "auto"},
        {"id": "D", "proveedor": "omniroute", "credencial": "TU_API_KEY_OMNIROUTE", "url": "http://x/v1"},
        {"id": "E", "proveedor": "omniroute", "credencial": "z", "url": "http://127.0.0.1:1/v1", "modelos": "auto"},
    ]}
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(cuentas, f); f.close()
    os.environ["NEUROTOK_CUENTAS"] = f.name
    p = wp.WorkerPool("cuentas.json")
    ids = [n.id for n in p.neuronas]
    assert ids[0] == "sim" and "plantilla" not in ids and not any(i.startswith(("D/", "E/")) for i in ids)
    assert sum(i.startswith("A/") for i in ids) == 3 and "B/ok-a" in ids and sum(i.startswith("C/") for i in ids) == 10
    s = p.snapshot()
    assert {"id", "proveedor", "rol", "estado", "cooldown_restante_s", "usos", "errores", "ultimo_error", "instancia"} <= set(s[0])
    assert s[0]["instancia"] == ""
    # A: ok-a, ok-b, ritmo (max 3). Forzamos que 'ritmo' salga primero y luego rote
    for n in p.neuronas: n.usos = 9
    for n in p.neuronas:
        if n.id == "A/ritmo": n.usos = 0
    t, n = agente(p)
    assert t and t.startswith("hola desde ok"), t
    d = {x["id"]: x for x in p.snapshot()}
    assert d["A/ritmo"]["estado"] == "EN_PAUSA" and 1 <= d["A/ritmo"]["cooldown_restante_s"] <= 2
    assert d["A/ok-a"]["estado"] == "DISPONIBLE"
    # C responde 429 siempre: tras 6 fallos seguidos se pausa la INSTANCIA entera
    for n in p.neuronas:
        n.usos = 99 if not n.id.startswith("C/") else 0
    agente(p, intentos=10)
    r = {i["id"]: i for i in p.resumen()["instancias"]}
    assert r["C"]["disponibles"] == 0 and r["C"]["en_pausa"] == 10, r["C"]
    assert r["C"]["proxima_libre_s"] >= 1 and "ritmo" in r["C"]["ultimo_error"]
    assert set(r) == {"A", "B", "C"} and r["A"]["total"] == 3 and r["A"]["url_corta"].startswith("127.0.0.1:")
    # cuota (3600+) y modelo no pausan la instancia A
    # instancia A cae: red => pausa de instancia, B sigue
    a.shutdown(); a.server_close()
    for n in p.neuronas:
        n.usos = 99
    for n in p.neuronas:
        if n.id == "A/ok-a": n.usos = 0
    agente(p, intentos=3)
    r = {i["id"]: i for i in p.resumen()["instancias"]}
    assert r["A"]["disponibles"] == 0 and r["A"]["en_pausa"] == 3 and "red" in r["A"]["ultimo_error"], r["A"]
    t, n = agente(p)
    assert n and n.id == "B/ok-a"
    assert p.seconds_until_available() >= 1
    # cooldown nunca acorta una pausa
    n0 = p.neuronas[0]; p.cooldown(n0, 100); h = n0.cooldown_hasta; p.cooldown(n0, 5); assert n0.cooldown_hasta == h
    # proveedores directos: 429 por cuota => pausa larga; por ritmo => igual que antes
    class R:
        def __init__(s, st, txt, h=None): s.status_code, s.text, s.headers, s.ok = st, txt, h or {}, st < 400
    try: wp._check(R(429, json.dumps({"error": {"code": "insufficient_quota", "message": "You exceeded your current quota"}})))
    except wp.RateLimitError as e: assert e.retry_after >= 3600
    try: wp._check(R(429, "slow down", {"retry-after": "7"}))
    except wp.RateLimitError as e: assert e.retry_after == 7
    try: wp._check(R(429, '{"retryDelay": "34s"}'))
    except wp.RateLimitError as e: assert e.retry_after == 35
    b.shutdown(); c.shutdown()


if __name__ == "__main__":
    test_todo(); print("OK: integración WorkerPool+OmniRoute")
