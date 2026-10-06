#!/usr/bin/env python3
"""fase_t4d.py - un 401/403 pausa al menos 30 min aunque el proveedor mande un Retry-After corto. Idempotente."""
import sys
from pathlib import Path
F = Path("backend/errores_llm.py")
OLD = '        return "auth", _acotar(hint if hint else DEF_AUTH)\n'
NEW = '        return "auth", _acotar(max(hint or 0, DEF_AUTH))  # una credencial mala no se arregla en segundos\n'
t = F.read_text(encoding="utf-8") if F.exists() else ""
if NEW in t:
    print("backend/errores_llm.py: ya aplicado"); sys.exit(0)
if t.count(OLD) != 1:
    print("ABORTADO, no se tocó nada -> no encuentro la línea de auth"); sys.exit(1)
t = t.replace(OLD, NEW, 1); compile(t, str(F), "exec"); F.write_text(t, encoding="utf-8")
print("backend/errores_llm.py: ok\nfase_t4d lista")
