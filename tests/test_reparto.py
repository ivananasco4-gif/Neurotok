import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from omniroute import repartir_por_proveedor as rp, es_modelo_chat


def test():
    ids = [f"aihorde/m{i}" for i in range(183)] + [f"dva/m{i}" for i in range(110)] + \
          [f"auto/m{i}" for i in range(45)] + ["groq/a", "groq/b", "gemini/x", "moonshot/y", "solo"]
    r = rp(ids, 100)
    assert len(r) == 100 and len(set(r)) == 100
    pref = {i.split("/")[0] for i in r}
    assert {"groq", "gemini", "moonshot", "aihorde", "dva", "auto"} <= pref and "solo" in r
    assert {"groq/a", "groq/b", "gemini/x", "moonshot/y"} <= set(r)          # los pequeños entran completos
    assert r.count("dva/m0") == 1 and "aihorde/m0" in r and "aihorde/m182" not in r  # orden interno conservado
    assert rp(["a", "b", "c"], 2) == ["a", "b"] and rp([], 5) == [] and len(rp(ids, 10**6)) == len(ids)
    assert not es_modelo_chat("veo-free/veo-3") and not es_modelo_chat("veoaifree-web/x") and es_modelo_chat("gemini/gemini-3.7-flash")


if __name__ == "__main__":
    test(); print("OK: reparto por proveedor")
