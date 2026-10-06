#!/usr/bin/env python3
"""fase_t4c.py - el tope max_modelos se reparte POR PROVEEDOR (por turnos), no por orden de lista.
Además descarta modelos de video (veo*). Idempotente; si algo no coincide no toca nada."""
import sys
from pathlib import Path

OM = Path("backend/omniroute.py")
E1 = ('            "speech", "ocr")\n', '            "speech", "ocr", "veo")\n')
E2 = ("def listar_modelos(url, credencial, timeout=15, max_modelos=100):\n", '''def repartir_por_proveedor(ids, maximo):
    """Elige hasta `maximo` ids repartiéndolos por turnos entre proveedores (prefijo antes de '/'),
    para que un proveedor con cientos de modelos no desplace a los demás. Conserva el orden dentro de cada uno."""
    maximo = max(1, int(maximo))
    grupos = {}
    for i in ids:
        grupos.setdefault(i.split("/", 1)[0] if "/" in i else "", []).append(i)
    cola = [list(g) for g in grupos.values()]
    out, k = [], 0
    while len(out) < maximo and any(cola):
        for g in cola:
            if g and len(out) < maximo:
                out.append(g.pop(0))
        k += 1
    return out


def listar_modelos(url, credencial, timeout=15, max_modelos=100):
''')
E3 = ("    return ids[:max(1, int(max_modelos))]\n", "    return repartir_por_proveedor(ids, max_modelos)\n")


def main():
    if not OM.exists():
        print("ABORTADO: no existe", OM); sys.exit(1)
    t = OM.read_text(encoding="utf-8")
    if "repartir_por_proveedor" in t:
        print("backend/omniroute.py: ya aplicado"); return
    for old, _ in (E1, E2, E3):
        if t.count(old) != 1:
            print("ABORTADO, no se tocó nada -> no coincide:", old.strip()[:60]); sys.exit(1)
    for old, new in (E1, E2, E3):
        t = t.replace(old, new, 1)
    compile(t, str(OM), "exec")
    OM.write_text(t, encoding="utf-8")
    print("backend/omniroute.py: ok\nfase_t4c lista")


main()
