import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from errores_llm import clasificar_error as ce

def test():
    for st in (401, 403):
        t, s = ce(st, {"Retry-After": "1"}, {"error": {"message": "Invalid API Key"}}); assert t == "auth" and s >= 1800, (t, s)
    t, s = ce(403, {"retry-after": "7200"}, "x"); assert t == "auth" and s == 7200
    assert ce(429, {"Retry-After": "1"}, {"error": {"code": "rate_limit_exceeded"}}) == ("ritmo", 1)

if __name__ == "__main__":
    test(); print("OK: auth con pausa mínima")
