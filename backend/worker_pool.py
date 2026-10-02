"""worker_pool.py - Pool de neuronas (cuentas/APIs) con rotación y cooldown ante 429."""
from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from sanitizer import register_secrets

DISPONIBLE, TRABAJANDO, EN_PAUSA = "DISPONIBLE", "TRABAJANDO", "EN_PAUSA"
DEFAULT_COOLDOWN = 60.0
TIMEOUT_HTTP = 90

OPENAI_COMPAT = {
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "llama-3.3-70b-versatile"),
    "deepseek": ("https://api.deepseek.com/chat/completions", "deepseek-chat"),
    "grok": ("https://api.x.ai/v1/chat/completions", "grok-4"),
    "qwen": ("https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions", "qwen-plus"),
    "kimi": ("https://api.moonshot.ai/v1/chat/completions", "moonshot-v1-8k"),
}
GEMINI_MODEL = "gemini-2.5-flash"
CLAUDE_MODEL = "claude-sonnet-4-5"


class RateLimitError(Exception):
    def __init__(self, retry_after: float = DEFAULT_COOLDOWN) -> None:
        super().__init__(f"429 rate limit (retry en {retry_after:.0f}s)")
        self.retry_after = retry_after


class AuthError(Exception):
    pass


class LLMError(Exception):
    pass


@dataclass
class Neurona:
    id: str
    proveedor: str
    credencial: str
    rol_sugerido: str = "creador"
    modelo: str = ""
    tipo_auth: str = "api_key"
    estado: str = DISPONIBLE
    cooldown_hasta: float = 0.0
    usos: int = 0
    errores: int = 0

    def cooldown_restante(self) -> int:
        return max(0, int(self.cooldown_hasta - time.time()))


class WorkerPool:
    def __init__(self, path: str = "cuentas.json") -> None:
        self._lock = threading.RLock()
        self.neuronas: list[Neurona] = []
        path = os.environ.get("NEUROTOK_CUENTAS", path)
        if not Path(path).exists():
            raise SystemExit("Falta cuentas.json: copia cuentas.example.json a cuentas.json y pon tus claves.")
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for c in data["cuentas"]:
            if c.get("tipo_auth", "api_key") != "api_key":
                print(f"[pool] {c['id']}: solo se admite tipo_auth=api_key. Omitida.")
                continue
            if c["credencial"].startswith("TU_"):
                continue  # plantilla sin completar
            self.neuronas.append(Neurona(
                id=c["id"], proveedor=c["proveedor"], credencial=c["credencial"],
                rol_sugerido=c.get("rol_sugerido", "creador"), modelo=c.get("modelo", ""),
            ))
        register_secrets(n.credencial for n in self.neuronas)

    def _refresh(self) -> None:
        now = time.time()
        for n in self.neuronas:
            if n.estado == EN_PAUSA and now >= n.cooldown_hasta:
                n.estado = DISPONIBLE

    def acquire(self, roles: list[str]) -> Neurona | None:
        """Devuelve una neurona DISPONIBLE, priorizando roles en orden; si no, cualquiera."""
        with self._lock:
            self._refresh()
            for rol in roles + [None]:
                for n in self.neuronas:
                    if n.estado == DISPONIBLE and (rol is None or n.rol_sugerido == rol):
                        n.estado = TRABAJANDO
                        n.usos += 1
                        return n
            return None

    def release(self, n: Neurona) -> None:
        with self._lock:
            if n.estado == TRABAJANDO:
                n.estado = DISPONIBLE

    def cooldown(self, n: Neurona, segundos: float = DEFAULT_COOLDOWN) -> None:
        with self._lock:
            n.estado = EN_PAUSA
            n.cooldown_hasta = time.time() + segundos
            n.errores += 1

    def seconds_until_available(self) -> float:
        with self._lock:
            self._refresh()
            esperas = [n.cooldown_hasta - time.time() for n in self.neuronas if n.estado == EN_PAUSA]
            return max(1.0, min(esperas)) if esperas else 5.0

    def snapshot(self) -> list[dict]:
        with self._lock:
            self._refresh()
            return [{
                "id": n.id, "proveedor": n.proveedor, "rol": n.rol_sugerido, "estado": n.estado,
                "cooldown_restante_s": n.cooldown_restante(), "usos": n.usos, "errores": n.errores,
            } for n in self.neuronas]


# ---------------------------------------------------------------- llamadas a proveedores
def _check(resp: requests.Response) -> None:
    if resp.status_code == 429:
        try:
            ra = float(resp.headers.get("retry-after", DEFAULT_COOLDOWN))
        except ValueError:
            ra = DEFAULT_COOLDOWN
        raise RateLimitError(ra)
    if resp.status_code in (401, 403):
        raise AuthError(f"HTTP {resp.status_code}: credencial inválida")
    if resp.status_code >= 500:
        raise RateLimitError(30.0)  # error del proveedor: pausa corta y rota
    if not resp.ok:
        raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")


# ---------------------------------------------------------------- proveedor "simulado" (pruebas sin API keys)
_SIM_N: dict = {}
_SIM_CALLS: dict = {}
_SIM_PLAN = ["Verificar el entorno", "Probar salida larga y un error", "Cerrar la tarea"]
_SIM_CMDS = [
    ['echo "Hola desde Neurotok"', "python --version"],
    ["seq 1 80", "ls carpeta_que_no_existe", "ls ~"],
    ['echo "Tarea terminada"'],
]


def _simulado(n: Neurona, system: str, user: str) -> str:
    """IA falsa con guion fijo: ejecuta comandos reales en Termux sin gastar cuota."""
    time.sleep(1.2)
    _SIM_N[n.id] = _SIM_N.get(n.id, 0) + 1
    if n.id == "crea_sim_1" and _SIM_N[n.id] == 2:
        raise RateLimitError(20.0)  # simula quedarse sin cuota: pasa a crea_sim_2
    if "Sub-Cerebro Arquitecto" in system:
        _SIM_CALLS.clear()
        return json.dumps({"pasos": _SIM_PLAN})
    m = re.search(r"Paso (\d+)/", user)
    i = int(m.group(1)) if m else 1
    cmds = _SIM_CMDS[(i - 1) % len(_SIM_CMDS)]
    k = _SIM_CALLS.get(i, 0)
    _SIM_CALLS[i] = k + 1
    if k < len(cmds):
        return json.dumps({"pensamiento": f"Simulación, paso {i}", "comando": cmds[k], "estado": "CONTINUAR"})
    return json.dumps({"pensamiento": "Paso completo", "comando": "", "estado": "FINALIZADO"})


def call_llm(n: Neurona, system: str, user: str) -> str:
    """Envía (system, user) y devuelve el texto de la respuesta."""
    p = n.proveedor
    if p == "simulado":
        return _simulado(n, system, user)
    try:
        if p == "gemini":
            model = n.modelo or GEMINI_MODEL
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": n.credencial},
                json={"systemInstruction": {"parts": [{"text": system}]},
                      "contents": [{"role": "user", "parts": [{"text": user}]}],
                      "generationConfig": {"responseMimeType": "application/json"}},
                timeout=TIMEOUT_HTTP)
            _check(r)
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        if p == "claude":
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": n.credencial, "anthropic-version": "2023-06-01"},
                json={"model": n.modelo or CLAUDE_MODEL, "max_tokens": 1500, "system": system,
                      "messages": [{"role": "user", "content": user}]},
                timeout=TIMEOUT_HTTP)
            _check(r)
            return r.json()["content"][0]["text"]
        if p in OPENAI_COMPAT:
            url, default_model = OPENAI_COMPAT[p]
            r = requests.post(
                url, headers={"Authorization": f"Bearer {n.credencial}"},
                json={"model": n.modelo or default_model, "max_tokens": 1500,
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": user}]},
                timeout=TIMEOUT_HTTP)
            _check(r)
            return r.json()["choices"][0]["message"]["content"]
    except requests.RequestException as e:
        raise RateLimitError(20.0) from e  # red caída: rota a otra neurona
    except (KeyError, IndexError, ValueError) as e:
        raise LLMError(f"Respuesta inesperada de {p}: {e}") from e
    raise LLMError(f"Proveedor no soportado: {p}")
