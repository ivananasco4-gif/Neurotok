"""sanitizer.py - Limpia la salida cruda de Termux y la convierte en Markdown compacto."""
from __future__ import annotations

import re
from dataclasses import dataclass

ANSI_RE = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]"            # CSI (colores, cursor)
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC (títulos)
    r"|\x1b[@-Z\\-_]"                       # otros escapes de 2 bytes
)

_NOISE = (
    r"\[[=#>\-\.\s]{5,}\]",                 # [====>    ]
    r"\b\d{1,3}(\.\d+)?%\s*[\|\[#=█▉▊▋▌▍▎▏]",   # 40%|████
    r"^\s*[\|/\\\-⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]\s*$",         # spinners
    r"^(Get|Hit|Ign|Fetched):\d*",           # apt
    r"^(Reading package lists|Building dependency tree|Reading state information)",
    r"^(Selecting previously|Preparing to unpack|Unpacking |Setting up |\(Reading database)",
    r"^npm (http|timing|sill|verb)",
    r"^\s*(Downloading|Collecting|Using cached|Requirement already satisfied)",
    r"\d+(\.\d+)?\s?[kMG]?i?B/s",           # velocidades
    r"\beta\s+\d+:\d+",
)
NOISE_RE = [re.compile(p, re.I) for p in _NOISE]
ERROR_RE = re.compile(
    r"error|fail|traceback|exception|fatal|cannot|can't|not found|denied|no such|warning", re.I
)

HEAD, TAIL, LIMIT = 5, 10, 25

_KNOWN: set[str] = set()
SECRET_RES = [re.compile(p) for p in (
    r"sk-[A-Za-z0-9_\-]{16,}", r"AIza[0-9A-Za-z_\-]{30,}", r"gsk_[A-Za-z0-9]{20,}",
    r"xai-[A-Za-z0-9]{20,}", r"gh[pousr]_[A-Za-z0-9]{30,}", r"github_pat_[A-Za-z0-9_]{30,}",
    r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}",
)]
KV_RE = re.compile(r"(?i)\b([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD)[A-Z0-9_]*)\s*[=:]\s*\S+")


def register_secrets(values) -> None:
    """Registra claves reales para borrarlas siempre del texto."""
    for v in values:
        if v and len(v) >= 8:
            _KNOWN.add(v)


def redact(text: str) -> str:
    text = text or ""
    for k in _KNOWN:
        text = text.replace(k, "[REDACTADO]")
    for rx in SECRET_RES:
        text = rx.sub("[REDACTADO]", text)
    return KV_RE.sub(r"\1=[REDACTADO]", text)


@dataclass
class SanitizedResult:
    markdown: str
    raw_chars: int
    clean_chars: int
    savings_pct: float


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def _resolve_cr(line: str) -> str:
    """Las barras de progreso reescriben la línea con \\r: nos quedamos con el último tramo."""
    parts = [p for p in line.split("\r") if p.strip()]
    return parts[-1] if parts else ""


def clean_lines(text: str) -> list[str]:
    text = strip_ansi(text or "").replace("\r\n", "\n")
    out: list[str] = []
    for raw in text.split("\n"):
        line = _resolve_cr(raw).rstrip()
        if not line.strip():
            continue
        if not ERROR_RE.search(line) and any(p.search(line) for p in NOISE_RE):
            continue
        out.append(line)
    return _dedupe(out)


def _dedupe(lines: list[str]) -> list[str]:
    res: list[str] = []
    count = 1
    for i, line in enumerate(lines):
        if i + 1 < len(lines) and lines[i + 1] == line:
            count += 1
            continue
        res.append(f"{line}  (x{count})" if count > 1 else line)
        count = 1
    return res


def truncate(lines: list[str]) -> list[str]:
    """>25 líneas: primeras 5 + últimas 10 (+ hasta 5 líneas de error de la zona omitida)."""
    if len(lines) <= LIMIT:
        return lines
    middle = lines[HEAD:-TAIL]
    hits = [l for l in middle if ERROR_RE.search(l)][:5]
    omitted = len(middle) - len(hits)
    aviso = f"... [{omitted} líneas omitidas por optimización de tokens] ..."
    return lines[:HEAD] + [aviso] + hits + lines[-TAIL:]


def sanitize(command: str, exit_code: int, stdout: str = "", stderr: str = "",
             timed_out: bool = False) -> SanitizedResult:
    command, stdout, stderr = redact(command), redact(stdout), redact(stderr)
    out_lines = truncate(clean_lines(stdout))
    err_lines = truncate(clean_lines(stderr))
    parts = [
        "### Comando ejecutado",
        f"`{command.strip()}`",
        f"**exit_code:** {exit_code}" + (" (TIMEOUT)" if timed_out else ""),
        "**stdout:**",
        "```text",
        "\n".join(out_lines) if out_lines else "(vacío)",
        "```",
    ]
    if err_lines:
        parts.append("**stderr:**")
        parts.extend(f"> {l}" for l in err_lines)
    md = "\n".join(parts)
    raw = len(stdout or "") + len(stderr or "")
    body = len("\n".join(out_lines)) + len("\n".join(err_lines))
    pct = max(0.0, (1 - body / raw) * 100) if raw > 0 else 0.0
    return SanitizedResult(md, raw, len(md), round(pct, 1))
