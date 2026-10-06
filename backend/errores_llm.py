"""Clasificador puro de errores de proveedores LLM (sin red, sin estado).

clasificar_error(status, headers, body, proveedor) -> (tipo, segundos)
tipo: "ritmo" | "cuota" | "auth" | "modelo" | "red" | "otro"
"""
import json
import re
import time
from email.utils import parsedate_to_datetime

DEF_RITMO = 20          # límite de ritmo sin pista: segundos
DEF_CUOTA = 6 * 3600    # cuota agotada sin pista: horas
DEF_CUOTA_DIA = 12 * 3600
DEF_AUTH = 1800
DEF_MODELO = 1800
DEF_RED = 30
DEF_OTRO = 10
MAX_PAUSA = 24 * 3600

_DUR = re.compile(r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m(?!s))?(?:(\d+(?:\.\d+)?)s)?(?:(\d+(?:\.\d+)?)ms)?$")


def _dur(txt):
    """'34s', '6m0s', '1h2m3.5s', '250ms', '12' -> segundos (float) o None."""
    if txt is None:
        return None
    t = str(txt).strip().lower()
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        pass
    m = _DUR.match(t)
    if not m or not any(m.groups()):
        return None
    h, mi, s, ms = (float(g) if g else 0.0 for g in m.groups())
    return h * 3600 + mi * 60 + s + ms / 1000.0


def _hdrs(headers):
    out = {}
    for k, v in (headers or {}).items():
        out[str(k).lower()] = v
    return out


def _retry_after(h, ahora=None):
    if "retry-after-ms" in h:
        v = _dur(h["retry-after-ms"])
        if v is not None:
            return v / 1000.0
    v = h.get("retry-after")
    if v is None:
        return None
    d = _dur(v)
    if d is not None:
        return d
    try:  # fecha HTTP
        dt = parsedate_to_datetime(str(v))
        return max(0.0, dt.timestamp() - (ahora if ahora is not None else time.time()))
    except Exception:
        return None


def _parse_body(body):
    if body is None:
        return {}, ""
    if isinstance(body, (bytes, bytearray)):
        body = body.decode("utf-8", "replace")
    if isinstance(body, dict):
        return body, json.dumps(body)
    txt = str(body)
    try:
        j = json.loads(txt)
        return (j if isinstance(j, dict) else {"_": j}), txt
    except Exception:
        return {}, txt


def _err_obj(j):
    e = j.get("error", j)
    if isinstance(e, list) and e:
        e = e[0]
    return e if isinstance(e, dict) else {"message": str(e)}


def _gemini_info(e):
    """(retryDelay_s|None, es_diaria bool) a partir de error.details de Gemini."""
    delay, diaria = None, False
    for d in e.get("details", []) or []:
        if not isinstance(d, dict):
            continue
        t = d.get("@type", "")
        if t.endswith("RetryInfo"):
            delay = _dur(d.get("retryDelay"))
        if t.endswith("QuotaFailure"):
            for v in d.get("violations", []) or []:
                s = (str(v.get("quotaId", "")) + str(v.get("quotaMetric", ""))).lower()
                if "perday" in s or "per_day" in s:
                    diaria = True
    return delay, diaria


_RE_TRY = re.compile(r"try again in\s+([0-9hms.\s]+?)(?:[.,;]|$|\s(?:[a-z]))", re.I)
_RE_DIA = re.compile(r"per day|\brpd\b|\btpd\b|daily|diari|por d[ií]a|free_tier_requests", re.I)
_RE_CUOTA = re.compile(
    r"insufficient_quota|exceeded your current quota|billing|credit balance|"
    r"out of credits|no credits|quota (?:exceeded|exhausted)|payment required|"
    r"monthly (?:limit|quota)|usage limit", re.I)
_RE_RITMO = re.compile(r"rate.?limit|too many requests|slow down|requests per (?:min|sec)|\brpm\b|\btpm\b", re.I)
_RE_MODELO = re.compile(r"model[_ ]?not[_ ]?found|does not exist|no such model|unknown model|"
                        r"model .{0,80}(?:not found|not supported|unavailable|deprecated|decommissioned)|"
                        r"not a valid model|invalid model", re.I)


def _acotar(s, minimo=1):
    return int(max(minimo, min(MAX_PAUSA, round(s))))


def clasificar_error(status, headers=None, body=None, proveedor=""):
    h = _hdrs(headers)
    j, txt = _parse_body(body)
    e = _err_obj(j)
    code = str(e.get("code", "") or "").lower()
    typ = str(e.get("type", "") or "").lower()
    gstatus = str(e.get("status", "") or "").upper()
    msg = str(e.get("message", "") or txt)[:2000]
    blob = f"{code} {typ} {gstatus} {msg}".lower()
    ra = _retry_after(h)
    g_delay, g_dia = _gemini_info(e)
    hint = ra if ra is not None else g_delay
    if hint is None:
        m = _RE_TRY.search(msg)
        if m:
            hint = _dur(re.sub(r"\s+", "", m.group(1)))
    if hint is None:  # cabeceras x-ratelimit-reset-*
        for k in ("x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"):
            if k in h:
                hint = _dur(h[k])
                if hint is not None:
                    break

    # sin respuesta HTTP: red
    if status in (None, 0):
        return "red", DEF_RED
    try:
        status = int(status)
    except (TypeError, ValueError):
        return "otro", DEF_OTRO

    cuota_txt = bool(_RE_CUOTA.search(blob)) or code == "insufficient_quota" or status == 402
    diaria = g_dia or bool(_RE_DIA.search(blob))

    if status in (401, 407) or (status == 403 and not cuota_txt and not _RE_RITMO.search(blob)
                                and "resource_exhausted" not in blob):
        return "auth", _acotar(max(hint or 0, DEF_AUTH))  # una credencial mala no se arregla en segundos
    if status == 402 or cuota_txt:
        return "cuota", _acotar(hint if hint else DEF_CUOTA)
    if status == 429 or "resource_exhausted" in blob or status == 403:
        if "rate_limit_exceeded" in blob and not diaria:
            return "ritmo", _acotar(hint if hint else DEF_RITMO)
        if diaria:
            # límite diario: horas, aunque la pista sea corta (Groq/Gemini avisan 'ya')
            seg = hint if (hint and hint >= 60) else DEF_CUOTA_DIA
            return "cuota", _acotar(seg)
        if hint and hint > 900:  # una pista >15 min ya no es un límite de ritmo
            return "cuota", _acotar(hint)
        return "ritmo", _acotar(hint if hint else DEF_RITMO)
    if status in (404, 410) or (status in (400, 422) and _RE_MODELO.search(blob)):
        return "modelo", _acotar(DEF_MODELO)
    if status in (408, 425, 502, 503, 504, 521, 522, 523, 524) or status == 529:
        return "red", _acotar(hint if hint else DEF_RED)
    if status >= 500:
        return "otro", _acotar(hint if hint else DEF_OTRO)
    return "otro", DEF_OTRO
