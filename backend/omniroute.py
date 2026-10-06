"""OmniRoute como proveedor: descubrimiento de modelos, llamada de chat y pool por instancias.

Una neurona = instancia + modelo (id "instancia/modelo").
Cooldown en dos niveles: modelo (ritmo/cuota/modelo) e instancia (red/auth).
Solo stdlib. No crea cuentas ni elude límites: solo reparte y respeta pausas.
"""
import json
import threading
import time
import urllib.error
import urllib.request

try:
    from errores_llm import clasificar_error
except ImportError:  # uso como paquete
    from .errores_llm import clasificar_error

_NO_CHAT = ("embed", "rerank", "whisper", "tts", "transcri", "moderation", "dall-e", "dalle",
            "image", "imagen", "flux", "stable-diffusion", "sdxl", "music", "video", "audio",
            "speech", "ocr", "veo")


def es_modelo_chat(entrada):
    """entrada: dict de /models (o str con el id). Conservador: descarta no-chat conocidos."""
    if isinstance(entrada, str):
        entrada = {"id": entrada}
    mid = str(entrada.get("id", "")).lower()
    if not mid:
        return False
    for k in ("type", "kind", "task", "object_type"):
        v = str(entrada.get(k, "")).lower()
        if v and v not in ("chat", "model", "llm", "text", "chat.completion", "chat_completion"):
            return False
    caps = entrada.get("capabilities") or entrada.get("modalities") or entrada.get("output_modalities")
    if isinstance(caps, (list, tuple)) and caps:
        c = [str(x).lower() for x in caps]
        if not any(x in ("chat", "text", "completion", "completions") for x in c):
            return False
    return not any(p in mid for p in _NO_CHAT)


def _req(url, credencial, datos=None, timeout=30):
    h = {"Accept": "application/json"}
    if credencial:
        h["Authorization"] = "Bearer " + credencial
    body = None
    if datos is not None:
        body = json.dumps(datos).encode()
        h["Content-Type"] = "application/json"
    h.setdefault("User-Agent", "Mozilla/5.0 (Neurotok)")
    return urllib.request.Request(url, data=body, headers=h)


def repartir_por_proveedor(ids, maximo):
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
    """GET {url}/models -> lista de ids de chat (sin duplicados, tope max_modelos)."""
    with urllib.request.urlopen(_req(url.rstrip("/") + "/models", credencial), timeout=timeout) as r:
        j = json.loads(r.read().decode("utf-8", "replace"))
    data = j.get("data", j) if isinstance(j, dict) else j
    ids, vistos = [], set()
    for e in data or []:
        if es_modelo_chat(e):
            mid = e if isinstance(e, str) else e["id"]
            if mid not in vistos:
                vistos.add(mid)
                ids.append(mid)
    return repartir_por_proveedor(ids, max_modelos)


def chat(url, credencial, modelo, mensajes, timeout=60, max_tokens=None):
    """Devuelve (texto, None) o (None, (tipo, segundos, detalle))."""
    datos = {"model": modelo, "messages": mensajes, "stream": False}
    if max_tokens:
        datos["max_tokens"] = max_tokens
    try:
        with urllib.request.urlopen(_req(url.rstrip("/") + "/chat/completions", credencial, datos),
                                    timeout=timeout) as r:
            j = json.loads(r.read().decode("utf-8", "replace"))
        return j["choices"][0]["message"]["content"] or "", None
    except urllib.error.HTTPError as e:
        try:
            cuerpo = e.read().decode("utf-8", "replace")
        except Exception:
            cuerpo = ""
        t, s = clasificar_error(e.code, dict(e.headers or {}), cuerpo, "omniroute")
        return None, (t, s, f"HTTP {e.code}")
    except (urllib.error.URLError, OSError, TimeoutError):
        t, s = clasificar_error(None, {}, "", "omniroute")
        return None, (t, s, "red")
    except (KeyError, IndexError, ValueError):
        return None, ("otro", 10, "respuesta inválida")


def url_corta(url):
    return url.replace("https://", "").replace("http://", "").split("/")[0]


class PoolOmniRoute:
    """Pool de neuronas instancia/modelo. Hilo-seguro. API: acquire/release/cooldown/snapshot."""

    def __init__(self, cuentas, reloj=time.time, listar=listar_modelos):
        self._lk = threading.Lock()
        self._t = reloj
        self.inst = {}     # id -> dict(cfg, hasta, ultimo_error)
        self.n = {}        # id neurona -> dict
        for c in cuentas:
            if c.get("proveedor") != "omniroute":
                continue
            iid = c["id"]
            self.inst[iid] = {"cfg": c, "hasta": 0.0, "ultimo_error": None}
            mods = c.get("modelos", "auto")
            if mods == "auto":
                try:
                    mods = listar(c["url"], c.get("credencial", ""), max_modelos=c.get("max_modelos", 100))
                except Exception as e:
                    mods = []
                    self.inst[iid].update(hasta=self._t() + 30, ultimo_error=f"models: {type(e).__name__}")
            for m in list(mods)[:int(c.get("max_modelos", 100))]:
                nid = f"{iid}/{m}"
                self.n[nid] = {"id": nid, "instancia": iid, "modelo": m, "rol": c.get("rol_sugerido", "creador"),
                               "usos": 0, "ocupada": False, "hasta": 0.0, "estado_err": None}

    def _libre(self, n, ahora):
        return (not n["ocupada"] and n["hasta"] <= ahora and self.inst[n["instancia"]]["hasta"] <= ahora)

    def acquire(self, rol=None, excluir=()):
        with self._lk:
            ahora = self._t()
            c = [n for n in self.n.values() if self._libre(n, ahora) and n["id"] not in excluir
                 and (rol is None or n["rol"] == rol)]
            if not c:
                return None
            n = min(c, key=lambda x: (x["usos"], x["id"]))   # menos usadas primero
            n["ocupada"] = True
            n["usos"] += 1
            return dict(n)

    def release(self, nid):
        with self._lk:
            if nid in self.n:
                self.n[nid]["ocupada"] = False

    def cooldown(self, nid, segundos, nivel="modelo", motivo=None):
        with self._lk:
            n = self.n.get(nid)
            if not n:
                return
            hasta = self._t() + segundos
            if nivel == "instancia":
                i = self.inst[n["instancia"]]
                i["hasta"] = max(i["hasta"], hasta)
                i["ultimo_error"] = motivo
            else:
                n["hasta"] = max(n["hasta"], hasta)
                n["estado_err"] = motivo
                self.inst[n["instancia"]]["ultimo_error"] = motivo

    def aplicar_error(self, nid, tipo, segundos, detalle=None):
        """Decide el nivel según el tipo clasificado."""
        nivel = "instancia" if tipo in ("red", "auth") else "modelo"
        if tipo == "otro":
            segundos = min(segundos, 10)
        self.cooldown(nid, segundos, nivel, f"{tipo}: {detalle or ''}".strip())

    def ejecutar(self, mensajes, rol=None, max_intentos=8, timeout=60):
        """Rota entre neuronas hasta obtener respuesta. -> (texto, neurona_id) o (None, ultimo_error)."""
        usadas, ult = set(), None
        for _ in range(max_intentos):
            n = self.acquire(rol, excluir=usadas)
            if not n:
                break
            usadas.add(n["id"])
            cfg = self.inst[n["instancia"]]["cfg"]
            try:
                txt, err = chat(cfg["url"], cfg.get("credencial", ""), n["modelo"], mensajes, timeout)
            finally:
                self.release(n["id"])
            if err is None:
                return txt, n["id"]
            ult = err
            self.aplicar_error(n["id"], *err)
        return None, ult

    def snapshot(self):
        with self._lk:
            ahora = self._t()
            out = []
            for n in self.n.values():
                ih = self.inst[n["instancia"]]["hasta"]
                resta = max(n["hasta"], ih) - ahora
                est = "trabajando" if n["ocupada"] else ("en_pausa" if resta > 0 else "libre")
                out.append({"id": n["id"], "instancia": n["instancia"], "modelo": n["modelo"],
                            "rol": n["rol"], "estado": est, "cooldown_s": max(0, int(resta + 0.999)),
                            "usos": n["usos"]})
            return out

    def resumen(self):
        snap = self.snapshot()
        res = []
        for iid, i in self.inst.items():
            ns = [x for x in snap if x["instancia"] == iid]
            pausa = [x["cooldown_s"] for x in ns if x["estado"] == "en_pausa"]
            res.append({"id": iid, "nombre": i["cfg"].get("nombre", iid),
                        "url_corta": url_corta(i["cfg"]["url"]), "total": len(ns),
                        "disponibles": sum(x["estado"] == "libre" for x in ns),
                        "trabajando": sum(x["estado"] == "trabajando" for x in ns),
                        "en_pausa": len(pausa), "proxima_libre_s": min(pausa) if pausa else 0,
                        "ultimo_error": i["ultimo_error"]})
        return {"instancias": res}
