#!/usr/bin/env python3
"""fase_t4b.py - pausas por PROVEEDOR (prefijo del id del modelo) en worker_pool.py. Idempotente.
Si algo no coincide, no toca nada. Ejecutar desde la raíz del repo."""
import sys
from pathlib import Path

WP = Path("backend/worker_pool.py")

A_OLD = "        self._fallos_inst: dict = {}\n"
A_NEW = ("        self._fallos_inst: dict = {}   # instancia -> proveedores con 401/403 sin éxito (clave de gateway mala)\n"
         "        self._prov_hasta: dict = {}    # (instancia, proveedor) -> epoch de fin de pausa\n"
         "        self._prov_err: dict = {}\n"
         "        self._prov_fallos: dict = {}   # (instancia, proveedor) -> modelos que fallaron desde el último éxito\n")
B_OLD = "                          and self._inst_hasta.get(n.instancia, 0.0) <= ahora]\n"
B_NEW = ("                          and self._inst_hasta.get(n.instancia, 0.0) <= ahora\n"
         "                          and self._prov_hasta.get(self._pk(n), 0.0) <= ahora]\n")
C_OLD = "            esperas += [h - time.time() for h in self._inst_hasta.values() if h > time.time()]\n"
C_NEW = C_OLD + "            esperas += [h - time.time() for h in self._prov_hasta.values() if h > time.time()]\n"

D_INI, D_FIN = "    def ok(self, n: Neurona) -> None:\n", "    def resumen(self) -> dict:\n"
D_NEW = '''    @staticmethod
    def _prov(n: Neurona) -> str:
        """Proveedor = prefijo del id del modelo en OmniRoute ('gemini/xxx' -> 'gemini')."""
        return n.modelo.split("/", 1)[0] if (n.instancia and "/" in n.modelo) else ""

    def _pk(self, n: Neurona):
        p = self._prov(n)
        return (n.instancia, p) if p else None

    def ok(self, n: Neurona) -> None:
        with self._lock:
            if n.instancia:
                self._fallos_inst.pop(n.instancia, None)
                k = self._pk(n)
                if k:
                    self._prov_fallos.pop(k, None)

    def pausar(self, n: Neurona, tipo: str, segundos: float, detalle: str = "") -> None:
        """Pausa en tres niveles:
        - instancia: red (no responde) o 401/403 en 3 proveedores distintos (clave de gateway mala)
        - proveedor: 401/403 de ese proveedor; o cuota (2 modelos) / ritmo (3 modelos) seguidos sin éxito
        - modelo: el resto; un 404 saca solo ese modelo por 6 h."""
        with self._lock:
            ahora, msg = time.time(), f"{tipo}: {detalle}"[:200]
            n.ultimo_error = msg
            n.errores += 1
            inst, k = n.instancia, self._pk(n)
            if inst:
                self._inst_err[inst] = msg
            if inst and tipo == "red":
                self._inst_hasta[inst] = max(self._inst_hasta.get(inst, 0.0), ahora + segundos)
                return
            if inst and tipo == "auth":
                if k:
                    self._prov_hasta[k] = max(self._prov_hasta.get(k, 0.0), ahora + segundos)
                    self._prov_err[k] = msg
                    malos = self._fallos_inst.setdefault(inst, set())
                    malos.add(k[1])
                    if len(malos) < 3:
                        return
                self._inst_hasta[inst] = max(self._inst_hasta.get(inst, 0.0), ahora + segundos)
                return
            if k and tipo in ("cuota", "ritmo"):
                vistos = self._prov_fallos.setdefault(k, set())
                vistos.add(n.modelo)
                if len(vistos) >= (2 if tipo == "cuota" else 3):
                    self._prov_hasta[k] = max(self._prov_hasta.get(k, 0.0), ahora + segundos)
                    self._prov_err[k] = msg
                    vistos.clear()
            if tipo == "modelo":
                segundos = max(segundos, 6 * 3600)
            n.estado = EN_PAUSA
            n.cooldown_hasta = max(n.cooldown_hasta, ahora + segundos)

'''

E_INI, E_FIN = "    def resumen(self) -> dict:\n", "\n\n# ---------------------------------------------------------------- llamadas a proveedores"
E_NEW = '''    def resumen(self) -> dict:
        with self._lock:
            snap = self.snapshot()
            ahora = time.time()
            out = []
            for iid, cfg in self._inst_cfg.items():
                ns = [x for x in snap if x.get("instancia") == iid]
                pausa = [x["cooldown_restante_s"] for x in ns if x["estado"] == EN_PAUSA]
                provs = sorted(({"proveedor": p, "cooldown_s": int(h - ahora), "motivo": self._prov_err.get((i, p), "")}
                                for (i, p), h in self._prov_hasta.items() if i == iid and h > ahora),
                               key=lambda d: d["cooldown_s"])
                out.append({
                    "id": iid, "nombre": cfg["nombre"],
                    "url_corta": cfg["url"].replace("https://", "").replace("http://", "").split("/")[0],
                    "total": len(ns),
                    "disponibles": sum(x["estado"] == DISPONIBLE for x in ns),
                    "trabajando": sum(x["estado"] == TRABAJANDO for x in ns),
                    "en_pausa": len(pausa), "proxima_libre_s": min(pausa) if pausa else 0,
                    "ultimo_error": self._inst_err.get(iid, ""),
                    "proveedores_en_pausa": provs,
                })
            return {"instancias": out}

    def snapshot(self) -> list[dict]:
        with self._lock:
            self._refresh()
            ahora = time.time()
            res = []
            for n in self.neuronas:
                ih = self._inst_hasta.get(n.instancia, 0.0)
                k = self._pk(n)
                ph = self._prov_hasta.get(k, 0.0)
                estado = EN_PAUSA if (n.estado == DISPONIBLE and max(ih, ph) > ahora) else n.estado
                err = n.ultimo_error
                if not err and ph > ahora:
                    err = self._prov_err.get(k, "")
                elif not err and ih > ahora:
                    err = self._inst_err.get(n.instancia, "")
                res.append({
                    "id": n.id, "proveedor": n.proveedor, "rol": n.rol_sugerido, "estado": estado,
                    "cooldown_restante_s": max(0, int(max(n.cooldown_hasta, ih, ph) - ahora)),
                    "usos": n.usos, "errores": n.errores, "ultimo_error": err,
                    "instancia": n.instancia, "origen": self._prov(n),
                })
            return res'''


def cortar(t, ini, fin):
    if t.count(ini) != 1 or t.count(fin) != 1:
        return None
    i = t.index(ini); j = t.index(fin, i + 1) if fin != ini else None
    return i, j


def main():
    if not WP.exists():
        print("ABORTADO: no existe", WP); sys.exit(1)
    t = WP.read_text(encoding="utf-8")
    if "_prov_hasta" in t:
        print("backend/worker_pool.py: ya aplicado"); return
    for old in (A_OLD, B_OLD, C_OLD):
        if t.count(old) != 1:
            print("ABORTADO, no se tocó nada -> bloque no coincide:", old.strip()[:70]); sys.exit(1)
    for ini, fin in ((D_INI, E_INI), (E_INI, E_FIN)):
        if t.count(ini) != 1 or t.count(fin) != 1 or t.index(ini) > t.index(fin):
            print("ABORTADO, no se tocó nada -> no encuentro:", ini.strip()[:50]); sys.exit(1)
    t = t.replace(A_OLD, A_NEW, 1).replace(B_OLD, B_NEW, 1).replace(C_OLD, C_NEW, 1)
    i, j = t.index(D_INI), t.index(E_INI)
    t = t[:i] + D_NEW + t[j:]
    i, j = t.index(E_INI), t.index(E_FIN)
    t = t[:i] + E_NEW + t[j:]
    compile(t, str(WP), "exec")
    WP.write_text(t, encoding="utf-8")
    print("backend/worker_pool.py: ok\nfase_t4b lista")


main()
