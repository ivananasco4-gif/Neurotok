"""prompt_filter.py - Filtro Markdown de ENTRADA: el pedido del humano ("cerebelo") se limpia y se
estructura antes de llegar al cerebro. Determinista (sin llamar a ninguna IA), solo librería estándar.
Seguro por diseño: nunca borra código, rutas ni URLs; solo quita saludos y cortesías, repetidos y
ruido de terminal. Desactivable con NEUROTOK_FILTRO=0."""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass

try:
    from sanitizer import redact as _redact
except Exception:  # noqa: BLE001
    _redact = None

A, B = "\ue000", "\ue001"          # marcas privadas para proteger fragmentos intocables
PH = re.compile(f"{A}(\\d+){B}")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
MAX_PARRAFO = 60                    # párrafo sin cercar de más de N líneas = texto pegado: 5 primeras + 10 últimas

RELLENO = re.compile(r"""(?ix)
  (?:^|(?<=[\s,.;:!?¿¡]))
  (?: hola | buenas(?:\s+(?:tardes|noches|d[ií]as))? | buen(?:os)?\s+d[ií]as | hey | oye | ok(?:ey)?
    | por\s+favor | porfa(?:vor)? | please | gracias(?:\s+de\s+antemano)? | muchas\s+gracias | thanks
    | si\s+(?:puedes|podes|podés) | si\s+no\s+es\s+molestia | te\s+agradezco | te\s+agradecer[ií]a )
  (?=$|[\s,;:!?]|\.(?:\s|$))""")


@dataclass
class Pedido:
    md: str          # Markdown compacto que recibe el cerebro (y que se guarda en la bóveda)
    titulo: str      # una línea, para estado, bóveda y notas
    raw_chars: int
    md_chars: int


def _redactar(t: str) -> str:
    if _redact:
        try:
            return str(_redact(t))
        except Exception:  # noqa: BLE001
            pass
    return t


def _truncar(lineas: list[str]) -> list[str]:
    if len(lineas) <= MAX_PARRAFO:
        return lineas
    return lineas[:5] + [f"[… {len(lineas) - 15} líneas omitidas]"] + lineas[-10:]


def _colapsar(lineas: list[str]) -> list[str]:
    """Líneas idénticas consecutivas -> una sola con (xN)."""
    out: list[str] = []
    n = 1
    for i, l in enumerate(lineas):
        if i + 1 < len(lineas) and lineas[i + 1] == l and l.strip():
            n += 1
            continue
        out.append(f"{l} (x{n})" if n > 1 else l)
        n = 1
    return out


def _limpiar_frase(s: str) -> str:
    s = RELLENO.sub(" ", s)
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    s = re.sub(r"([,;:])(\s*[,;:])+", r"\1", s)
    s = re.sub(r"([!?])\1{1,}", r"\1", s)
    s = re.sub(r"^[\s,.;:!?¿¡-]+", "", s)
    s = re.sub(r"[\s,;:.-]+$", "", s)
    return re.sub(r"\s{2,}", " ", s).strip()


def filtrar(texto: str) -> Pedido:
    raw = texto or ""
    if os.environ.get("NEUROTOK_FILTRO", "1") == "0":
        t = _redactar(raw).strip()
        md = f"**Objetivo:** {t}"
        return Pedido(md, t[:140], len(raw), len(md))

    if not raw.strip():
        return Pedido("Objetivo: (pedido vacío)", "Pedido vacío", len(raw), 24)
    t = unicodedata.normalize("NFC", raw).replace("\r\n", "\n").replace("\r", "\n")
    t = ANSI.sub("", t)
    t = _redactar(t)

    # 1) proteger lo que NO se debe tocar: bloques de código, `código`, URLs y rutas
    guardados: list[str] = []

    def guardar(m: re.Match) -> str:
        guardados.append(m.group(0))
        return f"{A}{len(guardados) - 1}{B}"

    t = re.sub(r"```.*?```", lambda m: guardar(m), t, flags=re.S)
    t = re.sub(r"`[^`\n]+`", guardar, t)
    t = re.sub(r"https?://\S+|(?:~|\.{1,2})?/[\w.\-~/]*[\w\-~/]|\b[\w\-]+(?:/[\w.\-]*[\w\-])+|\b[\w\-]+\.[A-Za-z]{1,5}\b",
               guardar, t)
    t = re.sub(r'"[^"\n]{1,120}"|\'[^\'\n]{1,80}\'', guardar, t)

    # 2) texto pegado sin cercar (muy largo): se trunca como hace el sanitizador, y se cerca
    parrafos = []
    for p in re.split(r"\n\s*\n", t):
        ls = [l.rstrip() for l in p.split("\n")]
        if len(ls) > MAX_PARRAFO:
            ini = next((i + 1 for i, l in enumerate(ls[:3]) if l.endswith(":")), 1)
            cabeza, resto = ls[:ini], ls[ini:]
            cola = [resto.pop()] if resto and resto[-1].rstrip().endswith(("?", "!")) else []
            resto = _truncar(_colapsar(resto))
            guardados.append("```\n" + "\n".join(resto) + "\n```")
            parrafos.append("\n".join(cabeza + [f"{A}{len(guardados) - 1}{B}"] + cola))
        else:
            parrafos.append("\n".join(_colapsar(ls)))
    t = "\n".join(parrafos)

    # 3) a elementos: viñetas se respetan, el resto se parte en frases
    items: list[str] = []
    for linea in t.split("\n"):
        l = linea.strip()
        if not l:
            continue
        m = re.match(r"^(?:[-*•]|\d+[.)])\s+(.*)$", l)
        frases = [m.group(1)] if m else re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡0-9" + A + "])", l)
        for f in frases:
            f = f if re.fullmatch(PH.pattern, f.strip()) else _limpiar_frase(f)
            if f:
                items.append(f)
    def volver(s: str) -> str:
        return PH.sub(lambda m: guardados[int(m.group(1))], s)

    vistos, unicos = set(), []
    for it in items:
        k = volver(it).lower().rstrip(".!?")
        if k not in vistos:
            vistos.add(k)
            unicos.append(it)

    # 4) Markdown: Objetivo = primera frase de texto; el resto, detalles; los bloques van tal cual
    idx = next((i for i, s in enumerate(unicos) if not re.fullmatch(PH.pattern, s)), None)
    if idx is None:
        obj = "Ver los datos adjuntos"
        resto = unicos
    else:
        obj = unicos[idx].rstrip(".:")
        resto = unicos[:idx] + unicos[idx + 1:]
    detalles = [s for s in resto if not re.fullmatch(PH.pattern, s)]
    bloques = [s for s in resto if re.fullmatch(PH.pattern, s)]
    # pedido de una sola frase: sin negritas (no engordar los pedidos cortos)
    partes = [f"{'**Objetivo:**' if (detalles or bloques) else 'Objetivo:'} {volver(obj)}"]
    if detalles:
        partes.append("**Detalles:**\n" + "\n".join(f"- {volver(s)}" for s in detalles))
    if bloques:
        partes.append("**Datos:**\n" + "\n".join(volver(s) for s in bloques))
    md = "\n\n".join(partes)
    titulo = re.sub(r"```.*?```", "…", volver(obj), flags=re.S)
    titulo = re.sub(r"\s+", " ", titulo).strip().rstrip(":")[:140] or "Pedido"
    return Pedido(md, titulo, len(raw), len(md))


if __name__ == "__main__":  # python backend/prompt_filter.py
    casos = {
        "cortés": "Hola, buenas tardes!!! Por favor crea una app de turnos con Expo. Gracias de antemano. "
                  "Necesito que use Supabase. Si puedes, que tenga login. Gracias.",
        "viñetas+código": "Arregla el script ~/neurotok/backend/api_server.py:\n- que no falle al arrancar\n- que loguee\n"
                          "```python\nprint('hola')\n```\nPor favor.",
        "log pegado": "El build falla, mira:\n" + "\n".join(f"npm WARN deprecated paquete{i % 3}" for i in range(120)) + "\nQué hago?",
        "corto": "crea hola.txt",
        "repetido": "Haz un backup. Haz un backup. Haz un backup de ~/proyectos_ia.",
    }
    for nombre, c in casos.items():
        p = filtrar(c)
        print(f"== {nombre}: {p.raw_chars} -> {p.md_chars} chars | titulo: {p.titulo}\n{p.md}\n")
