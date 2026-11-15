"""Cerebro -> sub-cerebros -> neuronas, de punta a punta con la IA simulada. Offline, sin claves.
Ejecutar desde la raíz: python3 tests/test_cerebro_neuronas.py"""
import json, os, sys, tempfile

TMP = tempfile.mkdtemp(prefix="neurotok_test_")
os.environ.update(BOVEDA_DIR=os.path.join(TMP, "boveda"), WORKDIR=os.path.join(TMP, "work"),
                  NEUROTOK_MODO="auto", NEUROTOK_CUENTAS=os.path.join(os.path.dirname(__file__), "..", "backend",
                                                                       "cuentas.simulado.json"))
os.environ.pop("NEUROTOK_TMUX", None)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import worker_pool as wp  # noqa: E402
import agent_loop as al  # noqa: E402
from vault_manager import VaultManager  # noqa: E402


def test_normalizar_plan():
    n = al.normalizar_plan
    assert n({"pasos": ["a", "b"]}, "x") == [{"titulo": "a", "sub_cerebro": "creador"},
                                             {"titulo": "b", "sub_cerebro": "creador"}]
    assert n({"pasos": [{"titulo": "t", "sub_cerebro": "Auditor"}, {"titulo": "u", "rol": "hacker"}]}, "x") == \
        [{"titulo": "t", "sub_cerebro": "auditor"}, {"titulo": "u", "sub_cerebro": "creador"}]
    assert n({"pasos": []}, "obj") == [{"titulo": "obj", "sub_cerebro": "creador"}]
    assert n({"pasos": [{"titulo": ""}, "  "]}, "obj")[0]["titulo"] == "obj"
    assert al.roles_para("arquitecto", 0) == ["arquitecto"]
    assert al.roles_para("arquitecto", 2) == ["auditor", "arquitecto"]
    assert al.roles_para("auditor", 3) == ["auditor"]


def test_cerebro_reservado():
    """Sin neuronas del rol pedido, trabaja otra neurona; el cerebro solo como último recurso."""
    pool = wp.WorkerPool()
    n = pool.acquire(["arquitecto"]); assert n.rol_sugerido == "arquitecto"; pool.release(n)
    for x in pool.neuronas:
        if x.rol_sugerido not in ("orquestador",) and x.rol_sugerido != "auditor":
            x.estado = wp.EN_PAUSA; x.cooldown_hasta = 1e12
    n = pool.acquire(["creador"]); assert n.rol_sugerido == "auditor", n  # no el cerebro
    n2 = pool.acquire(["creador"]); assert n2.rol_sugerido == "orquestador"  # último recurso
    pool.release(n); pool.release(n2)


def test_auto_reparte_roles():
    pool = wp.WorkerPool.__new__(wp.WorkerPool)
    pool.neuronas, pool._inst_cfg = [], {}
    pool._cargar_omniroute({"id": "o1", "proveedor": "omniroute", "credencial": "k", "url": "http://x/v1",
                            "modelos": [f"p{i % 3}/m{i}" for i in range(8)], "rol_sugerido": "auto"})
    roles = [n.rol_sugerido for n in pool.neuronas]
    assert set(roles) == {"creador", "auditor", "arquitecto"} and roles.count("creador") == 4, roles


def test_punta_a_punta():
    wp._SIM_N.clear()
    pool = wp.WorkerPool()
    loop = al.AgentLoop(pool, VaultManager())
    loop.run("probar el cerebro con neuronas")
    st = al.RUNTIME.status()
    assert st["estado"] == "FINALIZADO", st
    plan = st["plan"]
    assert [p["sub_cerebro"] for p in plan] == ["creador", "auditor", "creador"], plan
    assert all(p["estado"] == "ok" for p in plan), plan
    rol = {n.id: n.rol_sugerido for n in pool.neuronas}
    for p in plan:
        assert p["neuronas"], p
        assert all(rol[x] == p["sub_cerebro"] for x in p["neuronas"]), p  # trabajó el sub-cerebro asignado
        assert "gemini_sim" not in p["neuronas"]  # el cerebro no ejecuta pasos
    # crea_sim_1 simula 429 en su 2ª llamada: crea_sim_2 tomó el relevo
    assert any("crea_sim_2" in p["neuronas"] for p in plan)
    assert st["sub_cerebro_activo"] == ""


if __name__ == "__main__":
    test_normalizar_plan(); test_cerebro_reservado(); test_auto_reparte_roles(); test_punta_a_punta()
    print("OK: cerebro -> sub-cerebros -> neuronas")
