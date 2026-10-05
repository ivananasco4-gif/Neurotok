#!/usr/bin/env python3
"""fase_t4.py - integra OmniRoute en worker_pool.py y api_server.py (idempotente).
Si algo no coincide EXACTAMENTE, no toca nada y avisa. Ejecutar desde la raíz del repo."""
import json, sys
from pathlib import Path

WP, API, EX = Path("backend/worker_pool.py"), Path("backend/api_server.py"), Path("backend/cuentas.example.json")
MARCA = "_POOL_ACTIVO"

WP_EDITS = [
("from sanitizer import register_secrets\n",
 "from sanitizer import register_secrets\nfrom errores_llm import clasificar_error\nimport omniroute as _omni\n"),
("TIMEOUT_HTTP = 90\n",
 "TIMEOUT_HTTP = 90\n_POOL_ACTIVO = None  # lo fija WorkerPool; call_llm(omniroute) le avisa de pausas\n"),
('''    ultimo_error: str = ""

    def cooldown_restante(self) -> int:
''', '''    ultimo_error: str = ""
    instancia: str = ""   # id de la instancia OmniRoute ("" = proveedor directo)
    url: str = ""

    def cooldown_restante(self) -> int:
'''),
("        self.neuronas: list[Neurona] = []\n",
 "        self.neuronas: list[Neurona] = []\n"
 "        self._inst_hasta: dict = {}   # instancia -> epoch hasta el que está en pausa\n"
 "        self._inst_err: dict = {}\n        self._inst_cfg: dict = {}\n"
 "        self._usos_inst: dict = {}\n        self._fallos_inst: dict = {}\n"),
('''        for c in data["cuentas"]:
            if c.get("tipo_auth", "api_key") != "api_key":
''', '''        for c in data["cuentas"]:
            if c.get("proveedor") == "omniroute":
                self._cargar_omniroute(c)
                continue
            if c.get("tipo_auth", "api_key") != "api_key":
'''),
("        register_secrets(n.credencial for n in self.neuronas)\n",
 "        register_secrets(n.credencial for n in self.neuronas if n.credencial)\n"
 "        global _POOL_ACTIVO\n        _POOL_ACTIVO = self\n"),
('''                libres = [n for n in self.neuronas
                          if n.estado == DISPONIBLE and (rol is None or n.rol_sugerido == rol)]
                if libres:
                    n = min(libres, key=lambda x: x.usos)  # reparte el trabajo entre las neuronas
                    n.estado = TRABAJANDO
                    n.usos += 1
                    return n
''', '''                ahora = time.time()
                libres = [n for n in self.neuronas
                          if n.estado == DISPONIBLE and (rol is None or n.rol_sugerido == rol)
                          and self._inst_hasta.get(n.instancia, 0.0) <= ahora]
                if libres:
                    # reparte entre neuronas (menos usadas) y, a igualdad, entre instancias
                    n = min(libres, key=lambda x: (x.usos, self._usos_inst.get(x.instancia, 0)))
                    n.estado = TRABAJANDO
                    n.usos += 1
                    if n.instancia:
                        self._usos_inst[n.instancia] = self._usos_inst.get(n.instancia, 0) + 1
                    return n
'''),
("            n.cooldown_hasta = time.time() + segundos\n",
 "            n.cooldown_hasta = max(n.cooldown_hasta, time.time() + segundos)  # nunca acortar una pausa\n"),
("            esperas = [n.cooldown_hasta - time.time() for n in self.neuronas if n.estado == EN_PAUSA]\n",
 "            esperas = [n.cooldown_hasta - time.time() for n in self.neuronas if n.estado == EN_PAUSA]\n"
 "            esperas += [h - time.time() for h in self._inst_hasta.values() if h > time.time()]\n"),
("    def snapshot(self) -> list[dict]:\n", '''    # ---- OmniRoute: instancias, pausas en dos niveles y resumen
    def _cargar_omniroute(self, c: dict) -> None:
        cred = c.get("credencial", "")
        if cred.startswith(("TU_", "PEGA_")):
            return  # plantilla sin completar
        iid, url = c["id"], c["url"].rstrip("/")
        mx = max(1, int(c.get("max_modelos", 100)))
        mods = c.get("modelos", "auto")
        if mods == "auto":
            try:
                mods = _omni.listar_modelos(url, cred, max_modelos=mx)
            except Exception as e:
                print(f"[pool] {iid}: no pude listar modelos ({type(e).__name__}). Omitida; reinicia con la instancia arriba.")
                return
        self._inst_cfg[iid] = {"nombre": c.get("nombre", iid), "url": url}
        for m in list(mods)[:mx]:
            self.neuronas.append(Neurona(
                id=f"{iid}/{m}", proveedor="omniroute", credencial=cred,
                rol_sugerido=c.get("rol_sugerido", "creador"), modelo=m, instancia=iid, url=url))

    def ok(self, n: Neurona) -> None:
        with self._lock:
            if n.instancia:
                self._fallos_inst[n.instancia] = 0

    def pausar(self, n: Neurona, tipo: str, segundos: float, detalle: str = "") -> None:
        """Pausa por modelo (ritmo/cuota/modelo/otro) o por instancia (red/auth).
        6 fallos seguidos de ritmo/cuota en una instancia sin ningún éxito => pausa la instancia."""
        with self._lock:
            ahora, msg = time.time(), f"{tipo}: {detalle}"[:200]
            n.ultimo_error = msg
            n.errores += 1
            inst = n.instancia
            if inst:
                self._inst_err[inst] = msg
                self._fallos_inst[inst] = self._fallos_inst.get(inst, 0) + 1
            if inst and (tipo in ("red", "auth") or
                         (tipo in ("ritmo", "cuota") and self._fallos_inst[inst] >= 6)):
                self._inst_hasta[inst] = max(self._inst_hasta.get(inst, 0.0), ahora + segundos)
            else:
                n.estado = EN_PAUSA
                n.cooldown_hasta = max(n.cooldown_hasta, ahora + segundos)

    def resumen(self) -> dict:
        with self._lock:
            snap = self.snapshot()
            out = []
            for iid, cfg in self._inst_cfg.items():
                ns = [x for x in snap if x.get("instancia") == iid]
                pausa = [x["cooldown_restante_s"] for x in ns if x["estado"] == EN_PAUSA]
                out.append({
                    "id": iid, "nombre": cfg["nombre"],
                    "url_corta": cfg["url"].replace("https://", "").replace("http://", "").split("/")[0],
                    "total": len(ns),
                    "disponibles": sum(x["estado"] == DISPONIBLE for x in ns),
                    "trabajando": sum(x["estado"] == TRABAJANDO for x in ns),
                    "en_pausa": len(pausa), "proxima_libre_s": min(pausa) if pausa else 0,
                    "ultimo_error": self._inst_err.get(iid, ""),
                })
            return {"instancias": out}

    def snapshot(self) -> list[dict]:
'''),
('''            return [{
                "id": n.id, "proveedor": n.proveedor, "rol": n.rol_sugerido, "estado": n.estado,
                "cooldown_restante_s": n.cooldown_restante(), "usos": n.usos, "errores": n.errores,
                "ultimo_error": n.ultimo_error,
            } for n in self.neuronas]
''', '''            ahora = time.time()
            res = []
            for n in self.neuronas:
                ih = self._inst_hasta.get(n.instancia, 0.0)
                estado = EN_PAUSA if (n.estado == DISPONIBLE and ih > ahora) else n.estado
                res.append({
                    "id": n.id, "proveedor": n.proveedor, "rol": n.rol_sugerido, "estado": estado,
                    "cooldown_restante_s": max(0, int(max(n.cooldown_hasta, ih) - ahora)),
                    "usos": n.usos, "errores": n.errores,
                    "ultimo_error": n.ultimo_error or (self._inst_err.get(n.instancia, "") if ih > ahora else ""),
                    "instancia": n.instancia,
                })
            return res
'''),
('''    if resp.status_code == 429:
        raise RateLimitError(_espera(resp))
''', '''    if resp.status_code == 429:
        espera = _espera(resp)
        tipo, seg = clasificar_error(429, dict(resp.headers), resp.text, "")
        raise RateLimitError(max(espera, seg) if tipo == "cuota" else espera)  # cuota agotada = pausa larga
'''),
("def call_llm(n: Neurona, system: str, user: str) -> str:\n", '''def _call_omniroute(n: Neurona, system: str, user: str) -> str:
    txt, err = _omni.chat(n.url, n.credencial, n.modelo,
                          [{"role": "system", "content": system}, {"role": "user", "content": user}],
                          timeout=TIMEOUT_HTTP, max_tokens=1500)
    pool = _POOL_ACTIVO
    if err is None:
        if pool:
            pool.ok(n)
        return txt
    tipo, seg, det = err
    if pool:
        pool.pausar(n, tipo, seg, det)
    if tipo in ("ritmo", "cuota", "red"):
        raise RateLimitError(float(seg))
    if tipo == "auth":
        raise AuthError(f"{det}: credencial inválida o sin permiso")
    if tipo == "modelo":
        raise ModelError(det)
    raise LLMError(det)


def call_llm(n: Neurona, system: str, user: str) -> str:
'''),
('''    if p == "simulado":
        return _simulado(n, system, user)
    try:
''', '''    if p == "simulado":
        return _simulado(n, system, user)
    if p == "omniroute":
        return _call_omniroute(n, system, user)
    try:
'''),
]

API_EDITS = [
("def get_neurons() -> dict:\n",
 "def get_neurons_resumen() -> dict:\n    return pool.resumen()\n\n\ndef get_neurons() -> dict:\n"),
('    "/neurons": get_neurons,\n',
 '    "/neurons": get_neurons,\n    "/neurons/resumen": get_neurons_resumen,\n'),
]

EX_EDIT = ('''      "modelo": "grok-4",
      "estado": "DISPONIBLE"
    }
  ]
}''', '''      "modelo": "grok-4",
      "estado": "DISPONIBLE"
    },
    {
      "id": "omni_01",
      "nombre": "OmniRoute 1",
      "proveedor": "omniroute",
      "tipo_auth": "api_key",
      "credencial": "TU_API_KEY_OMNIROUTE",
      "url": "http://HOST:20128/v1",
      "modelos": "auto",
      "max_modelos": 100,
      "rol_sugerido": "creador"
    }
  ]
}''')


def plan(path, edits, ya):
    if not path.exists():
        return None, f"no existe {path}"
    t = path.read_text(encoding="utf-8")
    if ya(t):
        return t, "ya aplicado"
    for old, _ in edits:
        if t.count(old) != 1:
            return None, f"{path}: bloque no coincide exacto ({t.count(old)} veces): {old.strip().splitlines()[0][:70]!r}"
    for old, new in edits:
        t = t.replace(old, new, 1)
    return t, "ok"


def main():
    trabajos = [(WP, WP_EDITS, lambda t: MARCA in t), (API, API_EDITS, lambda t: "get_neurons_resumen" in t),
                (EX, [EX_EDIT], lambda t: "omniroute" in t)]
    res = []
    for p, e, ya in trabajos:
        t, msg = plan(p, e, ya)
        if t is None:
            print("ABORTADO, no se tocó nada ->", msg); sys.exit(1)
        res.append((p, t, msg))
    try:
        json.loads(res[2][1])
    except Exception as ex:
        print("ABORTADO: el JSON de ejemplo quedaría inválido", ex); sys.exit(1)
    for p, t, msg in res:
        if msg == "ok":
            p.write_text(t, encoding="utf-8")
        print(f"{p}: {msg}")
    for p in (WP, API):
        compile(p.read_text(encoding="utf-8"), str(p), "exec")  # sintaxis
    print("fase_t4 lista")


main()
