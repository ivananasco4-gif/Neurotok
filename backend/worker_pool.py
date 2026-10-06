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
from errores_llm import clasificar_error
import omniroute as _omni

DISPONIBLE, TRABAJANDO, EN_PAUSA = "DISPONIBLE", "TRABAJANDO", "EN_PAUSA"
DEFAULT_COOLDOWN = 60.0
TIMEOUT_HTTP = 90
_POOL_ACTIVO = None  # lo fija WorkerPool; call_llm(omniroute) le avisa de pausas

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


class ModelError(LLMError):
    """Modelo inexistente o petición mal formada (HTTP 400/404): no sirve reintentar con esta neurona."""


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
    ultimo_error: str = ""
    instancia: str = ""   # id de la instancia OmniRoute ("" = proveedor directo)
    url: str = ""

    def cooldown_restante(self) -> int:
        return max(0, int(self.cooldown_hasta - time.time()))


class WorkerPool:
    def __init__(self, path: str = "cuentas.json") -> None:
        self._lock = threading.RLock()
        self.neuronas: list[Neurona] = []
        self._inst_hasta: dict = {}   # instancia -> epoch hasta el que está en pausa
        self._inst_err: dict = {}
        self._inst_cfg: dict = {}
        self._usos_inst: dict = {}
        self._fallos_inst: dict = {}   # instancia -> proveedores con 401/403 sin éxito (clave de gateway mala)
        self._prov_hasta: dict = {}    # (instancia, proveedor) -> epoch de fin de pausa
        self._prov_err: dict = {}
        self._prov_fallos: dict = {}   # (instancia, proveedor) -> modelos que fallaron desde el último éxito
        path = os.environ.get("NEUROTOK_CUENTAS", path)
        if not Path(path).exists():
            raise SystemExit("Falta cuentas.json: copia cuentas.example.json a cuentas.json y pon tus claves.")
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for c in data["cuentas"]:
            if c.get("proveedor") == "omniroute":
                self._cargar_omniroute(c)
                continue
            if c.get("tipo_auth", "api_key") != "api_key":
                print(f"[pool] {c['id']}: solo se admite tipo_auth=api_key. Omitida.")
                continue
            if c["credencial"].startswith("TU_"):
                continue  # plantilla sin completar
            self.neuronas.append(Neurona(
                id=c["id"], proveedor=c["proveedor"], credencial=c["credencial"],
                rol_sugerido=c.get("rol_sugerido", "creador"), modelo=c.get("modelo", ""),
            ))
        register_secrets(n.credencial for n in self.neuronas if n.credencial)
        global _POOL_ACTIVO
        _POOL_ACTIVO = self

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
                ahora = time.time()
                libres = [n for n in self.neuronas
                          if n.estado == DISPONIBLE and (rol is None or n.rol_sugerido == rol)
                          and self._inst_hasta.get(n.instancia, 0.0) <= ahora
                          and self._prov_hasta.get(self._pk(n), 0.0) <= ahora]
                if libres:
                    # reparte entre neuronas (menos usadas) y, a igualdad, entre instancias
                    n = min(libres, key=lambda x: (x.usos, self._usos_inst.get(x.instancia, 0)))
                    n.estado = TRABAJANDO
                    n.usos += 1
                    if n.instancia:
                        self._usos_inst[n.instancia] = self._usos_inst.get(n.instancia, 0) + 1
                    return n
            return None

    def release(self, n: Neurona) -> None:
        with self._lock:
            if n.estado == TRABAJANDO:
                n.estado = DISPONIBLE

    def cooldown(self, n: Neurona, segundos: float = DEFAULT_COOLDOWN, motivo: str = "") -> None:
        with self._lock:
            if motivo:
                n.ultimo_error = motivo[:200]
            n.estado = EN_PAUSA
            n.cooldown_hasta = max(n.cooldown_hasta, time.time() + segundos)  # nunca acortar una pausa
            n.errores += 1

    def seconds_until_available(self) -> float:
        with self._lock:
            self._refresh()
            esperas = [n.cooldown_hasta - time.time() for n in self.neuronas if n.estado == EN_PAUSA]
            esperas += [h - time.time() for h in self._inst_hasta.values() if h > time.time()]
            esperas += [h - time.time() for h in self._prov_hasta.values() if h > time.time()]
            return max(1.0, min(esperas)) if esperas else 5.0

    # ---- OmniRoute: instancias, pausas en dos niveles y resumen
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

    @staticmethod
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

    def resumen(self) -> dict:
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
            return res

# ---------------------------------------------------------------- llamadas a proveedores
def _espera(resp: requests.Response) -> float:
    """Cuánto esperar tras un 429: cabecera, 'retryDelay' de Gemini, o 1 h si la cuota es diaria."""
    ra = resp.headers.get("retry-after")
    try:
        if ra:
            return min(float(ra), 21600.0)
    except ValueError:
        pass
    m = re.search(r'retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', resp.text)
    if m:
        return min(float(m.group(1)) + 1, 21600.0)
    low = resp.text.lower()
    if any(k in low for k in ("perday", "per day", "per_day", "daily")):
        return 3600.0
    return DEFAULT_COOLDOWN


def _check(resp: requests.Response) -> None:
    if resp.status_code == 429:
        espera = _espera(resp)
        tipo, seg = clasificar_error(429, dict(resp.headers), resp.text, "")
        raise RateLimitError(max(espera, seg) if tipo == "cuota" else espera)  # cuota agotada = pausa larga
    low = resp.text[:500].lower()
    if resp.status_code in (401, 403) or "api key not valid" in low or "api_key_invalid" in low:
        raise AuthError(f"HTTP {resp.status_code}: credencial inválida o sin permiso")
    if resp.status_code >= 500:
        raise RateLimitError(30.0)  # error del proveedor: pausa corta y rota
    if resp.status_code in (400, 404):
        raise ModelError(f"HTTP {resp.status_code}: {resp.text[:300]}")
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


def _call_omniroute(n: Neurona, system: str, user: str) -> str:
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
    """Envía (system, user) y devuelve el texto de la respuesta."""
    p = n.proveedor
    if p == "simulado":
        return _simulado(n, system, user)
    if p == "omniroute":
        return _call_omniroute(n, system, user)
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
                url, headers={"Authorization": f"Bearer {n.credencial}", "User-Agent": "Mozilla/5.0 (Neurotok)"},
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
