"""Pausas por proveedor (prefijo del modelo). Offline. Ejecutar desde la raíz: python3 tests/test_pausa_proveedor.py"""
import json, os, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import worker_pool as wp


def servidor(todo_401=False):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _s(self, c, o, h=None):
            b = json.dumps(o).encode(); self.send_response(c)
            for k, v in (h or {}).items(): self.send_header(k, v)
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def do_POST(self):
            m = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["model"]
            if todo_401: return self._s(401, {"error": {"message": "invalid gateway key"}})
            if m.startswith("moonshot/"): return self._s(402, {"error": {"message": "insufficient balance"}})
            if m.startswith("groq/"): return self._s(403, {"error": {"message": "Invalid API Key"}})
            if m == "dead/gone": return self._s(404, {"error": {"code": "model_not_found", "message": "model does not exist"}})
            if m == "gemini/limited": return self._s(429, {"error": {"code": "rate_limit_exceeded"}}, {"Retry-After": "2"})
            self._s(200, {"choices": [{"message": {"content": "ok " + m}}]})
    s = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=s.serve_forever, daemon=True).start(); return s


def llamar(p, nid):
    n = next(x for x in p.neuronas if x.id == nid)
    n.estado = wp.TRABAJANDO
    try:
        return wp.call_llm(n, "s", "u")
    except wp.RateLimitError as e: p.cooldown(n, e.retry_after, str(e))
    except wp.AuthError as e: p.cooldown(n, 3600, str(e))
    except wp.ModelError as e: p.cooldown(n, 600, str(e))
    except wp.LLMError as e: p.cooldown(n, 60, str(e))
    finally: p.release(n)


def test_todo():
    s1, s2 = servidor(), servidor(todo_401=True)
    u = lambda s: "http://127.0.0.1:%d/v1" % s.server_port
    mods = ["gemini/ok", "gemini/ok2", "gemini/limited", "moonshot/m1", "moonshot/m2", "moonshot/m3", "moonshot/m4",
            "groq/q1", "groq/q2", "groq/q3", "dead/gone", "dead/otro", "combo-sin-prefijo"]
    cuentas = {"cuentas": [
        {"id": "O", "proveedor": "omniroute", "credencial": "k", "url": u(s1), "modelos": mods},
        {"id": "G", "proveedor": "omniroute", "credencial": "k", "url": u(s2), "modelos": ["a/x", "b/x", "c/x", "d/x"]}]}
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(cuentas, f); f.close()
    os.environ["NEUROTOK_CUENTAS"] = f.name
    p = wp.WorkerPool("x")
    est = lambda: {x["id"]: x for x in p.snapshot()}
    # 1) moonshot sin saldo (402): 1er fallo = solo ese modelo; 2º = TODO moonshot; gemini intacto
    assert llamar(p, "O/moonshot/m1") is None
    e = est(); assert e["O/moonshot/m1"]["estado"] == "EN_PAUSA" and e["O/moonshot/m2"]["estado"] == "DISPONIBLE"
    llamar(p, "O/moonshot/m2")
    e = est()
    assert all(e["O/moonshot/m%d" % i]["estado"] == "EN_PAUSA" and e["O/moonshot/m%d" % i]["cooldown_restante_s"] >= 3600 for i in (1, 2, 3, 4))
    assert all(e[x]["estado"] == "DISPONIBLE" for x in ("O/gemini/ok", "O/groq/q1", "O/dead/gone", "O/combo-sin-prefijo"))
    assert e["O/moonshot/m3"]["origen"] == "moonshot" and e["O/combo-sin-prefijo"]["origen"] == ""
    # 2) groq 403: un solo fallo pausa todo groq; no toca gemini
    llamar(p, "O/groq/q1")
    e = est(); assert all(e["O/groq/q%d" % i]["estado"] == "EN_PAUSA" for i in (1, 2, 3)) and e["O/gemini/ok"]["estado"] == "DISPONIBLE"
    # 3) 404: solo ese modelo, por horas; el otro 'dead' sigue
    llamar(p, "O/dead/gone")
    e = est(); assert e["O/dead/gone"]["cooldown_restante_s"] >= 6 * 3600 - 5 and e["O/dead/otro"]["estado"] == "DISPONIBLE"
    # 4) ritmo en un modelo de gemini: solo ese; gemini/ok sigue y responde
    llamar(p, "O/gemini/limited")
    e = est(); assert e["O/gemini/limited"]["estado"] == "EN_PAUSA" and e["O/gemini/ok"]["estado"] == "DISPONIBLE"
    assert llamar(p, "O/gemini/ok") == "ok gemini/ok"
    # 5) resumen
    r = {i["id"]: i for i in p.resumen()["instancias"]}["O"]
    nombres = {x["proveedor"] for x in r["proveedores_en_pausa"]}
    assert nombres == {"moonshot", "groq"}, nombres
    assert r["total"] == 13 and r["disponibles"] >= 3 and r["en_pausa"] >= 8
    # 6) acquire nunca entrega neuronas de proveedores en pausa
    vistos = set()
    for _ in range(40):
        n = p.acquire([]) 
        if not n: break
        vistos.add(n.id)
    for x in p.neuronas: p.release(x)
    assert not any(("moonshot" in v or "groq" in v) for v in vistos), vistos
    # 7) clave de gateway mala (401 en 3 proveedores distintos) => pausa la INSTANCIA
    for nid in ("G/a/x", "G/b/x"): llamar(p, nid)
    assert {i["id"]: i for i in p.resumen()["instancias"]}["G"]["disponibles"] == 2
    llamar(p, "G/c/x")
    r = {i["id"]: i for i in p.resumen()["instancias"]}["G"]
    assert r["disponibles"] == 0 and r["en_pausa"] == 4, r
    # 8) éxito limpia la cuenta de fallos del proveedor
    p2k = ("O", "gemini"); assert p2k not in p._prov_hasta
    s1.shutdown(); s2.shutdown()


if __name__ == "__main__":
    test_todo(); print("OK: pausas por proveedor")
