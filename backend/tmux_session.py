"""tmux_session.py - Ejecuta comandos dentro de una sesion tmux VISIBLE y devuelve lo capturado.

    from tmux_session import TmuxSession, available
    s = TmuxSession("neurotok", cwd="~/proyectos_ia")
    code, out, err, timed_out = s.run("ls -la", timeout=60)   # misma forma que AgentLoop._execute
    s.close()

El usuario puede mirar lo que pasa con:  tmux attach -t neurotok

COMO FUNCIONA (por que es fiable)
- El texto del comando NUNCA se escribe en el terminal: Python lo guarda en un archivo y a la sesion
  solo se le envia una linea corta con la ruta de un "runner". Asi comillas, heredocs, `$`, `!` o
  saltos de linea no los reinterpreta ni tmux ni readline.
- No se lee la pantalla (nada de capture-pane): stdout y stderr se capturan en archivos separados con
  `tee` (y se ven en vivo en el panel). El fin del comando lo marca un archivo `rc_<id>` con el exit
  code, escrito de forma atomica. No hay sleeps a ciegas ni heuristicas de silencio.
- Cada comando corre en su propio `bash` hijo, empezando en `cwd` y con stdin cerrado (igual que
  `AgentLoop._execute`): `cd`/`export` no se arrastran de un comando al siguiente. Si algo pregunta por
  teclado, recibe EOF en vez de colgarse.
- Timeout: Ctrl-C a la sesion; se comprueba que la shell responde (sonda con su propio marcador);
  si no, Ctrl-C otra vez, Ctrl-\\ y, como ultimo recurso, se recrea la sesion.
- Si la sesion muere (kill-session, `exit`, reinicio de tmux) se recrea en la siguiente llamada.
- Solo se ejecuta lo recibido. La politica de comandos bloqueados la aplica quien llama.

Solo tmux + libreria estandar. Termux: pkg install tmux. Autoprueba: python backend/tmux_session.py
"""
from __future__ import annotations

import atexit
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid

# Variables de entorno que NO se heredan en la sesion (solo se usan sus NOMBRES; nunca se imprimen valores)
SENSIBLE = re.compile(r"(KEY|TOKEN|SECRET|PASS|CREDENTIAL|AUTH)", re.I)
NOMBRE_VAR = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
RUTA_SEGURA = re.compile(r"[\w./+-]+")   # sin espacios, comillas ni '!' (la linea viaja por readline)
CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

RUNNER = r"""D=@@D@@
I=@@I@@
cat -- "$D/hdr_$I"
if cd -- @@CWD@@ 2>/dev/null; then
@@ENV@@  @@SHELL@@ "$D/cmd_$I" </dev/null > >(tee "$D/out_$I"; : > "$D/oend_$I") 2> >(tee "$D/err_$I" >&2; : > "$D/eend_$I")
  rc=$?
else
  echo "[tmux] no se pudo entrar en el directorio de trabajo" >&2
  : > "$D/oend_$I"; : > "$D/eend_$I"; rc=1
fi
printf '%s' "$rc" > "$D/rc_$I.tmp" && mv -f "$D/rc_$I.tmp" "$D/rc_$I"
"""


def available() -> bool:
    """True si hay tmux instalado."""
    return shutil.which("tmux") is not None


class TmuxSession:
    def __init__(self, name: str = "neurotok", cwd: str | None = None, shell: str | None = None,
                 scrub_env: bool = True, max_salida: int = 2_000_000, env: dict | None = None) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", name or ""):
            raise ValueError("name: solo letras, numeros, '_' y '-' (max 40)")
        self.name = name
        self.cwd = os.path.abspath(os.path.expanduser(cwd)) if cwd else os.getcwd()
        self.shell = shell or shutil.which("bash") or "sh"
        self._bash = shutil.which("bash")   # el runner usa sustitucion de procesos: requiere bash
        self.scrub_env = scrub_env
        # variables que se exportan a CADA comando (solo en su bash hijo; no tocan la shell del panel)
        self.env = {k: str(v) for k, v in (env or {}).items() if NOMBRE_VAR.fullmatch(str(k))}
        self.max_salida = max(10_000, int(max_salida))
        self._lock = threading.RLock()
        self._dir: str | None = None
        self._atexit = False

    # ------------------------------------------------------------------ tmux de bajo nivel
    def _tmux(self, *args: str, timeout: float = 10) -> tuple[int, str, str]:
        try:
            r = subprocess.run(["tmux", *args], capture_output=True, text=True, timeout=timeout,
                               stdin=subprocess.DEVNULL)
            return r.returncode, r.stdout, r.stderr
        except (OSError, subprocess.TimeoutExpired) as e:
            return 127, "", str(e)

    def _existe(self) -> bool:
        return self._tmux("has-session", "-t", "=" + self.name)[0] == 0

    def _enviar_linea(self, texto: str) -> bool:
        """Escribe una linea literal en la sesion y pulsa Enter (solo se usa con texto propio y corto)."""
        t = f"{self.name}:"
        if self._tmux("send-keys", "-t", t, "-l", "--", texto)[0] != 0:
            return False
        return self._tmux("send-keys", "-t", t, "Enter")[0] == 0

    def _tecla(self, tecla: str) -> None:
        self._tmux("send-keys", "-t", f"{self.name}:", tecla)

    # ------------------------------------------------------------------ ciclo de vida
    def _carpeta(self) -> str:
        if self._dir and os.path.isdir(self._dir):
            return self._dir
        base = tempfile.gettempdir()
        if not RUTA_SEGURA.fullmatch(base):
            base = os.path.join(os.path.expanduser("~"), ".cache")
            os.makedirs(base, exist_ok=True)
        self._dir = tempfile.mkdtemp(prefix="nt-", dir=base)   # 0700
        if not self._atexit:   # al salir: cerrar la sesion y borrar temporales (sin procesos ni archivos huerfanos)
            atexit.register(self.close)
            self._atexit = True
        if not RUTA_SEGURA.fullmatch(self._dir):
            raise RuntimeError("ruta temporal con caracteres no permitidos: " + self._dir)
        return self._dir

    def _shell_inicial(self) -> str:
        partes: list[str] = []
        if self.scrub_env:
            nombres = sorted(n for n in os.environ if SENSIBLE.search(n) and NOMBRE_VAR.fullmatch(n))
            if nombres:
                partes = ["env"] + [x for n in nombres for x in ("-u", n)]
        partes.append(self.shell)
        if os.path.basename(self.shell) == "bash":
            partes += ["--noprofile", "--norc"]
        return " ".join(shlex.quote(p) for p in partes)

    def _esperar_archivo(self, ruta: str, segundos: float) -> bool:
        fin = time.monotonic() + segundos
        while True:
            if os.path.exists(ruta):
                return True
            if time.monotonic() >= fin:
                return False
            time.sleep(0.02)

    def _sondear(self, segundos: float) -> bool:
        """True si la shell de la sesion esta libre y responde (marcador propio, no por silencio)."""
        marca = os.path.join(self._carpeta(), f"ready_{uuid.uuid4().hex[:8]}")
        if not self._enviar_linea(f": > {shlex.quote(marca)}"):
            return False
        ok = self._esperar_archivo(marca, segundos)
        if ok:
            try:
                os.unlink(marca)
            except OSError:
                pass
        return ok

    def _crear(self) -> None:
        if not os.path.isdir(self.cwd):
            raise RuntimeError(f"el directorio de trabajo no existe: {self.cwd}")
        self._carpeta()
        rc, _, err = self._tmux("new-session", "-d", "-s", self.name, "-x", "200", "-y", "50",
                                "-c", self.cwd, self._shell_inicial())
        if rc != 0:
            raise RuntimeError("no se pudo crear la sesion tmux: " + (err.strip() or f"codigo {rc}"))
        if not self._sondear(10):
            self._tmux("kill-session", "-t", "=" + self.name)
            raise RuntimeError("la sesion tmux no respondio al arrancar")

    def ensure(self) -> None:
        """Crea la sesion si no existe (o si murio)."""
        if not available():
            raise RuntimeError("tmux no esta instalado (en Termux: pkg install tmux)")
        if not self._bash:
            raise RuntimeError("bash no esta instalado (en Termux: pkg install bash)")
        with self._lock:
            if not self._existe():
                self._crear()

    def _reiniciar(self) -> None:
        self._tmux("kill-session", "-t", "=" + self.name)
        self._crear()

    def close(self) -> None:
        """Cierra la sesion y borra los archivos temporales."""
        with self._lock:
            if available() and self._existe():
                self._tmux("kill-session", "-t", "=" + self.name)
            if self._dir:
                shutil.rmtree(self._dir, ignore_errors=True)
                self._dir = None

    def __enter__(self) -> "TmuxSession":
        self.ensure()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------ ejecucion
    @staticmethod
    def _cabecera(cmd: str) -> str:
        lineas = [CTRL.sub("?", x)[:200] for x in cmd.splitlines()]
        txt = "\n$ " + "\n> ".join(lineas[:8])
        if len(lineas) > 8:
            txt += f"\n[... {len(lineas) - 8} lineas mas]"
        return txt + "\n"

    @staticmethod
    def _escribir(ruta: str, texto: str) -> None:
        fd = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)

    def _leer(self, ruta: str) -> str:
        """Lee un archivo de salida; si pasa de max_salida conserva el principio y, sobre todo, el final."""
        try:
            tam = os.path.getsize(ruta)
            with open(ruta, "rb") as f:
                if tam <= self.max_salida:
                    datos = f.read()
                else:
                    cabeza = self.max_salida * 3 // 10
                    cola = self.max_salida - cabeza
                    ini = f.read(cabeza)
                    f.seek(tam - cola)
                    fin = f.read(cola)
                    datos = ini + f"\n[... {tam - self.max_salida} bytes omitidos ...]\n".encode() + fin
        except OSError:
            return ""
        return datos.decode("utf-8", errors="replace")

    @staticmethod
    def _barrer(d: str) -> None:
        """Borra archivos temporales de mas de 10 min (marcadores tardios de procesos en segundo plano)."""
        limite = time.time() - 600
        try:
            for n in os.listdir(d):
                p = os.path.join(d, n)
                try:
                    if os.path.getmtime(p) < limite:
                        os.unlink(p)
                except OSError:
                    pass
        except OSError:
            pass

    def _interrumpir(self) -> bool:
        """Tras un timeout: Ctrl-C, Ctrl-C, Ctrl-\\ y, si nada, recrear. True si la shell quedo libre."""
        for tecla in ("C-c", "C-c", "C-\\"):
            self._tecla(tecla)
            time.sleep(0.3)  # Ctrl-C vacia la cola de entrada del terminal: la sonda va despues
            if self._sondear(3):
                return True
        return False

    def run(self, cmd: str, timeout: int = 120) -> tuple[int, str, str, bool]:
        """Ejecuta `cmd` y devuelve (exit_code, stdout, stderr, timed_out).
        Timeout -> exit 124 y timed_out=True (con lo capturado hasta ese momento).
        Sesion muerta durante el comando -> exit 255. Fallos propios del modulo -> exit 1 con '[tmux] ...'."""
        if not isinstance(cmd, str):
            raise TypeError("cmd debe ser str")
        if "\x00" in cmd:
            return 1, "", "[tmux] el comando contiene un byte nulo", False
        if not cmd.strip():
            return 0, "", "", False
        with self._lock:
            try:
                self.ensure()
                if not os.path.isdir(self.cwd):
                    return 1, "", f"[tmux] el directorio de trabajo no existe: {self.cwd}", False
                d = self._carpeta()
            except (RuntimeError, OSError) as e:
                return 1, "", f"[tmux] {e}", False
            self._barrer(d)
            i = uuid.uuid4().hex[:8]
            ruta = lambda k: os.path.join(d, f"{k}_{i}")  # noqa: E731
            try:
                self._escribir(ruta("cmd"), cmd if cmd.endswith("\n") else cmd + "\n")
                self._escribir(ruta("hdr"), self._cabecera(cmd))
                self._escribir(ruta("run"), (RUNNER.replace("@@D@@", shlex.quote(d)).replace("@@I@@", i)
                                             .replace("@@CWD@@", shlex.quote(self.cwd))
                                             .replace("@@ENV@@", "".join(f"  export {k}={shlex.quote(v)}\n" for k, v in self.env.items()))
                                             .replace("@@SHELL@@", shlex.quote(self.shell))))
                if not self._enviar_linea(f"{shlex.quote(self._bash)} {shlex.quote(ruta('run'))}"):
                    return 1, "", "[tmux] no se pudo escribir en la sesion", False
                estado = self._esperar(ruta("rc"), timeout)
                timed_out = estado == "timeout"
                extra = ""
                if estado == "ok":  # el comando termino: dejar que tee vacie los dos flujos (con tope)
                    fin = time.monotonic() + 3
                    while time.monotonic() < fin and not (os.path.exists(ruta("oend")) and os.path.exists(ruta("eend"))):
                        time.sleep(0.01)
                    try:
                        code = int(open(ruta("rc")).read().strip() or 1)
                    except (OSError, ValueError):
                        code = 1
                elif timed_out:
                    code = 124
                    if not self._interrumpir():
                        extra = "[tmux] la sesion no respondio al timeout y se recreo"
                        self._reiniciar()
                else:  # sesion muerta durante el comando
                    code = 255
                    extra = "[tmux] la sesion termino durante el comando"
                out, err = self._leer(ruta("out")), self._leer(ruta("err"))
                if extra:
                    err = (err + ("\n" if err and not err.endswith("\n") else "") + extra + "\n")
                return code, out, err, timed_out
            except OSError as e:
                return 1, "", f"[tmux] error de archivos: {e}", False
            finally:
                for k in ("cmd", "hdr", "run", "out", "err", "oend", "eend", "rc", "rc.tmp"):
                    try:
                        os.unlink(ruta(k))
                    except OSError:
                        pass

    def _esperar(self, rc: str, timeout: float | None) -> str:
        """'ok' (hay rc), 'timeout' o 'muerta' (la sesion ya no existe)."""
        fin = time.monotonic() + (timeout if timeout and timeout > 0 else 10 ** 9)
        ultimo = time.monotonic()
        while True:
            if os.path.exists(rc):
                return "ok"
            ahora = time.monotonic()
            if ahora >= fin:
                return "timeout"
            if ahora - ultimo >= 1.0:
                ultimo = ahora
                if not self._existe():
                    return "muerta"
            time.sleep(0.02)


# ====================================================================== autoprueba
def _autoprueba() -> int:
    if not available():
        print("tmux no esta instalado: en Termux ejecuta  pkg install tmux  y vuelve a probar.")
        return 2
    nombre = f"neurotok-test-{os.getpid()}"
    trabajo = tempfile.mkdtemp(prefix="nt-cwd-")
    os.environ["NT_PRUEBA_SECRET_KEY"] = "valor-que-no-debe-heredarse"   # solo para la prueba
    s = TmuxSession(nombre, cwd=trabajo)
    fallos: list[str] = []

    PANEL = 'while read k v; do [ "$k" = PPid: ] && echo "$v"; done < /proc/$PPID/status'

    def prueba(titulo: str, cond: bool, detalle: str = "") -> None:
        print(("  OK   " if cond else "  FALLA ") + titulo + ("" if cond else f"  -> {detalle}"))
        if not cond:
            fallos.append(titulo)

    try:
        print(f"Sesion de prueba: {nombre}  (puedes verla con: tmux attach -t {nombre})")
        c, o, e, t = s.run("echo hola")
        prueba("echo simple", (c, o, e, t) == (0, "hola\n", "", False), repr((c, o, e, t)))
        c, o, e, t = s.run("true")
        prueba("exit code 0", c == 0 and not t, str(c))
        c, o, e, t = s.run("echo fuera; echo dentro >&2; exit 7")
        prueba("exit code distinto de 0 y stdout/stderr separados", (c, o, e) == (7, "fuera\n", "dentro\n"), repr((c, o, e)))
        c, o, e, t = s.run("comando_que_no_existe_xyz")
        prueba("comando inexistente (127 y 'not found' en stderr)", c == 127 and "not found" in e and o == "", repr((c, o, e)))
        multi = "cat <<'EOF'\nlinea \"con comillas\" y 'simples' y $HOME y `backticks` y \\ barra y !bang\nEOF\necho fin"
        c, o, e, t = s.run(multi)
        esperado = "linea \"con comillas\" y 'simples' y $HOME y `backticks` y \\ barra y !bang\nfin\n"
        prueba("multilinea con heredoc, comillas y caracteres especiales intactos", c == 0 and o == esperado, repr(o))
        c, o, e, t = s.run("printf '%s\\n' 'a$b' \"c'd\" '*?[x]' 'ñ€→' ';&|<>'")
        prueba("caracteres especiales y unicode", c == 0 and o == "a$b\nc'd\n*?[x]\nñ€→\n;&|<>\n", repr(o))
        t0 = time.monotonic()
        c, o, e, t = s.run("seq 1 3000", timeout=60)
        lineas = o.splitlines()
        prueba("3000 lineas de salida (sin perder el final)", c == 0 and len(lineas) == 3000 and lineas[0] == "1" and lineas[-1] == "3000",
               f"{len(lineas)} lineas")
        c, o, e, t = s.run("seq 1 20000", timeout=90)
        prueba("20000 lineas de salida", c == 0 and o.splitlines()[-1] == "20000", f"{len(o.splitlines())} lineas")
        c, o, e, t = s.run("head -c 200000 /dev/zero | tr '\\0' x; echo", timeout=60)
        prueba("una linea de 200 KB", c == 0 and len(o.strip()) == 200000, str(len(o)))
        s_env = TmuxSession(nombre + "-env", cwd=trabajo, env={"NT_X": "a b'c", "NT_Y": "$HOME"})
        c, o, e, t = s_env.run("echo \"[$NT_X][$NT_Y]\"")
        s_env.close()
        prueba("env: variables exportadas a cada comando (con comillas y $ intactos)", o == "[a b'c][$HOME]\n", repr((c, o, e)))
        c, o, e, t = s.run("read x; echo \"[$x]\"", timeout=20)
        prueba("stdin cerrado: no se cuelga esperando teclado", c == 0 and o == "[]\n", repr((c, o)))
        c, o, e, t = s.run("pwd; cd /; export NT_FOO=1")
        c2, o2, e2, t2 = s.run("pwd; echo \"[${NT_FOO:-vacio}]\"")
        p1 = o.splitlines()[0] if o else ""
        prueba("cwd correcto y comandos aislados entre si",
               os.path.realpath(p1) == os.path.realpath(trabajo) and o2.splitlines() == [p1, "[vacio]"], repr((o, o2)))
        c, o, e, t = s.run("exit 3")
        prueba("`exit` dentro del comando no mata la sesion", c == 3, str(c))
        left = [x for x in os.listdir(s._dir) if not x.startswith("ready_")]
        prueba("no quedan archivos temporales de comandos", left == [], repr(left))
        pid0 = s.run(PANEL)[1].strip()
        t0 = time.monotonic()
        c, o, e, t = s.run("echo antes; sleep 29", timeout=2)
        dur = time.monotonic() - t0
        prueba("timeout: interrumpe, devuelve 124/timed_out y lo capturado", t and c == 124 and "antes" in o and dur < 8, f"{(c, t, o, round(dur, 1))}")
        c, o, e, t = s.run("echo despues")
        prueba("tras el timeout la sesion sigue usable", (c, o, t) == (0, "despues\n", False), repr((c, o, e)))
        pid1 = s.run(PANEL)[1].strip()
        prueba("el timeout se resolvio con Ctrl-C: la sesion NO se recreo", pid0.isdigit() and pid0 == pid1, f"{pid0} -> {pid1}")
        if shutil.which("pgrep"):
            time.sleep(0.5)
            r = subprocess.run(["pgrep", "-f", "sleep 29"], capture_output=True, text=True)
            prueba("sin procesos huerfanos tras el timeout", r.stdout.strip() == "", r.stdout)
        t0 = time.monotonic()
        c, o, e, t = s.run("trap '' INT; echo terco; sleep 28", timeout=2)
        c2, o2, e2, t2 = s.run("echo libre")
        dur = time.monotonic() - t0
        prueba("un proceso que ignora Ctrl-C: se escala (Ctrl-C, Ctrl-\\, recrear) y la sesion queda usable",
               t and c == 124 and (c2, o2) == (0, "libre\n") and dur < 20, repr((c, t, o, c2, o2, round(dur, 1))))
        t0 = time.monotonic()
        c, o, e, t = s.run("(sleep 1; echo tarde) & echo ya")
        prueba("salida que llega justo despues del comando (se espera a que tee vacie)", (c, o) == (0, "ya\ntarde\n"), repr((c, o)))
        t1 = time.monotonic()
        c, o, e, t = s.run("(sleep 14) & echo rapido")
        dur = time.monotonic() - t1
        prueba("un proceso en segundo plano que retiene la salida no cuelga la llamada", (c, o) == (0, "rapido\n") and dur < 8, repr((c, o, round(dur, 1))))
        viejo = os.path.join(s._dir, "oend_antiguo")
        open(viejo, "w").close()
        os.utime(viejo, (time.time() - 3600, time.time() - 3600))
        s.run("true")
        prueba("se barren los archivos temporales viejos", not os.path.exists(viejo))
        subprocess.run(["tmux", "kill-session", "-t", "=" + nombre], capture_output=True)
        c, o, e, t = s.run("echo renacio")
        prueba("reinicio tras `tmux kill-session`", (c, o, t) == (0, "renacio\n", False), repr((c, o, e)))
        c, o, e, t = s.run('kill -9 "$(while read k v; do [ "$k" = PPid: ] && echo "$v"; done < /proc/$PPID/status)"; sleep 5', timeout=20)
        c2, o2, e2, t2 = s.run("echo vivo")
        prueba("si el comando mata la shell del panel: lo detecta (255) y la sesion se recrea",
               c == 255 and (c2, o2) == (0, "vivo\n"), repr((c, o, e, c2, o2, e2)))
        c, o, e, t = s.run("echo \"[${NT_PRUEBA_SECRET_KEY:-vacio}]\"; env | grep -c valor-que-no-debe || true")
        prueba("las variables sensibles no se heredan en la sesion", o.splitlines()[:1] == ["[vacio]"] and "valor-que" not in o, repr(o))
        resultados: dict[int, tuple] = {}
        hilos = [threading.Thread(target=lambda k=k: resultados.__setitem__(k, s.run(f"sleep 0.2; echo hilo{k}")))
                 for k in range(4)]
        [h.start() for h in hilos]
        [h.join() for h in hilos]
        prueba("llamadas concurrentes: cada una recibe su propia salida",
               all(resultados.get(k, (9, "", "", 0))[:2] == (0, f"hilo{k}\n") for k in range(4)), repr(resultados))
        s2 = TmuxSession(nombre, cwd=trabajo, max_salida=10_000)
        c, o, e, t = s2.run("seq 1 5000")
        prueba("salida enorme recortada conservando el final", "bytes omitidos" in o and o.rstrip().endswith("5000") and len(o) < 12_000, f"{len(o)} bytes")
    finally:
        s.close()
        shutil.rmtree(trabajo, ignore_errors=True)
    print("\nRESULTADO:", "TODO OK" if not fallos else f"{len(fallos)} FALLO(S): " + "; ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(_autoprueba())
