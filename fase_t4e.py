import sys
UA = '"User-Agent": "Mozilla/5.0 (Neurotok)"'
cambios = [
 ("backend/omniroute.py",
  '    return urllib.request.Request(url, data=body, headers=h)',
  '    h.setdefault("User-Agent", "Mozilla/5.0 (Neurotok)")\n    return urllib.request.Request(url, data=body, headers=h)'),
 ("backend/worker_pool.py",
  'url, headers={"Authorization": f"Bearer {n.credencial}"},',
  'url, headers={"Authorization": f"Bearer {n.credencial}", ' + UA + '},'),
]
nuevos = {}
for ruta, old, new in cambios:
    t = open(ruta, encoding="utf-8").read()
    if new in t:
        print("ya aplicado:", ruta); continue
    if t.count(old) != 1:
        print("ABORTO: no coincide exacto en", ruta, "(", t.count(old), "veces )"); sys.exit(1)
    nuevos[ruta] = t.replace(old, new)
for ruta, t in nuevos.items():
    open(ruta, "w", encoding="utf-8").write(t); print("parchado:", ruta)
