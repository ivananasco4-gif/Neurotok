"""vault_manager.py - Bóveda Markdown (~/boveda_ia): única fuente de verdad del proyecto."""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path


def _cut(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


class VaultManager:
    ESTADO = "00_estado_actual.md"
    BITACORA = "01_bitacora.md"
    METRICS = "metrics.json"

    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or os.environ.get("BOVEDA_DIR", "~/boveda_ia")).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not (self.root / self.BITACORA).exists():
            self._write(self.BITACORA, "# Bitácora\n")
        if not (self.root / self.METRICS).exists():
            self._write(self.METRICS, json.dumps({"raw_chars": 0, "clean_chars": 0}))

    # ---- utilidades internas
    def _write(self, name: str, content: str) -> None:
        tmp = self.root / (name + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(self.root / name)

    def _read(self, name: str) -> str:
        p = self.root / name
        return p.read_text(encoding="utf-8") if p.exists() else ""

    # ---- estado vivo (<200 tokens)
    def update_state(self, objetivo: str, paso: int, total: int,
                     ultima_accion: str, pendiente: str) -> None:
        md = (
            "# Estado actual\n"
            f"**Objetivo General:** {_cut(objetivo, 200)}\n"
            f"**Paso Actual:** {paso} de {total}\n"
            f"**Última Acción y Resultado:** {_cut(ultima_accion, 350)}\n"
            f"**Tarea Pendiente Inmediata:** {_cut(pendiente, 200)}\n"
        )
        with self._lock:
            self._write(self.ESTADO, md)

    def read_context(self) -> str:
        return self._read(self.ESTADO) or "(Sin estado previo)"

    # ---- bitácora
    def append_log(self, iteracion: int, neurona: str, pensamiento: str, salida_md: str) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = (
            f"\n## [{ts}] Iteración {iteracion} - {neurona}\n"
            f"**Pensamiento:** {_cut(pensamiento, 500)}\n\n{salida_md}\n"
        )
        with self._lock:
            with open(self.root / self.BITACORA, "a", encoding="utf-8") as f:
                f.write(entry)

    # ---- métricas de ahorro
    def record_savings(self, raw_chars: int, clean_chars: int) -> None:
        with self._lock:
            try:
                m = json.loads(self._read(self.METRICS))
            except json.JSONDecodeError:
                m = {"raw_chars": 0, "clean_chars": 0}
            m["raw_chars"] += raw_chars
            m["clean_chars"] += clean_chars
            self._write(self.METRICS, json.dumps(m))

    def metrics(self) -> dict:
        try:
            m = json.loads(self._read(self.METRICS))
        except json.JSONDecodeError:
            m = {"raw_chars": 0, "clean_chars": 0}
        raw, clean = m["raw_chars"], m["clean_chars"]
        m["tokens_crudos_aprox"] = raw // 4
        m["tokens_limpios_aprox"] = clean // 4
        m["ahorro_pct"] = round((1 - clean / raw) * 100, 1) if raw and clean < raw else 0.0
        return m
