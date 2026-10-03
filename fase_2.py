#!/usr/bin/env python3
"""Aplicador idempotente de Neurotok Tarea 2: Chat + Terminal."""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parent
# El script se ejecuta desde ~/neurotok; permitir también colocarlo temporalmente en otro sitio.
if (Path.cwd() / "app_fuente").is_dir():
    ROOT = Path.cwd()

EXPECTED = {
    "app_fuente/App.js": "335d4f78166631c70b48ebccbd2a45ba931400a0",
    "app_fuente/src/api.js": "1f3ff5d9491d2198a8da381bb5b3460e1bef609f",
    "app_fuente/src/mock.js": "466f032e13c0563a9b9086f3414c2c7585111ba4",
}

CHAT = r'''import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { getChat, postChat } from './api';
import { demoChatInit, demoChatSend, demoChatTick } from './mock';
import { T } from './theme';

export default function Chat({ mode, url }) {
  const [messages, setMessages] = useState(() => mode === 'demo' ? demoChatInit().mensajes : []);
  const [text, setText] = useState('');
  const [err, setErr] = useState('');
  const [sending, setSending] = useState(false);
  const desde = useRef(0);
  const demo = useRef(demoChatInit());

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        if (mode === 'demo') {
          demo.current = demoChatTick(demo.current);
          if (alive) setMessages(demo.current.mensajes);
          return;
        }
        const d = await getChat(url, desde.current);
        if (!alive) return;
        if (Array.isArray(d.mensajes) && d.mensajes.length) {
          setMessages((old) => [...old, ...d.mensajes.filter((m) => !old.some((x) => x.n === m.n))]);
        }
        if (Number.isInteger(d.siguiente)) desde.current = d.siguiente;
        setErr('');
      } catch (e) { if (alive) setErr(String(e.message || e)); }
    };
    tick();
    const id = setInterval(tick, 700);
    return () => { alive = false; clearInterval(id); };
  }, [mode, url]);

  const send = async () => {
    const value = text.trim();
    if (!value || sending) return;
    setSending(true); setErr(''); setText('');
    try {
      if (mode === 'demo') {
        demo.current = demoChatSend(demo.current, value);
        setMessages(demo.current.mensajes);
      } else {
        await postChat(url, value);
      }
    } catch (e) { setErr(String(e.message || e)); setText(value); }
    finally { setSending(false); }
  };

  return <View style={s.root}>
    <ScrollView contentContainerStyle={s.list}>
      <Text style={s.title}>Chat con el cerebro</Text>
      <Text style={s.mut}>{mode === 'demo' ? 'Demo · respuestas simuladas' : 'API · consulta en vivo'}</Text>
      {messages.map((m, i) => <View key={`${m.n ?? i}-${i}`} style={[s.bubble, m.rol === 'tu' ? s.you : m.rol === 'sistema' ? s.system : s.brain]}>
        <Text style={s.role}>{m.rol.toUpperCase()} · {m.t || ''}</Text>
        <Text style={s.text}>{m.texto}</Text>
      </View>)}
      {!!err && <Text style={s.error}>⚠ {err}</Text>}
    </ScrollView>
    <View style={s.composer}>
      <TextInput style={s.input} value={text} onChangeText={setText} multiline placeholder="Habla con el cerebro…"
        placeholderTextColor={T.mut} onSubmitEditing={send} editable={!sending} />
      <TouchableOpacity style={s.send} onPress={send} disabled={sending}>
        {sending ? <ActivityIndicator color={T.nodeTxt} /> : <Text style={s.sendText}>Enviar</Text>}
      </TouchableOpacity>
    </View>
  </View>;
}

const s = StyleSheet.create({
  root: { flex: 1 }, list: { padding: 14, paddingBottom: 20 }, title: { color: T.txt, fontSize: 16, fontWeight: '700', marginBottom: 3 },
  mut: { color: T.mut, fontSize: 12, marginBottom: 12 }, bubble: { maxWidth: '92%', borderWidth: 1, borderColor: T.line, borderRadius: 10, padding: 11, marginBottom: 9 },
  you: { alignSelf: 'flex-end', backgroundColor: T.panel }, brain: { alignSelf: 'flex-start', backgroundColor: T.panel }, system: { alignSelf: 'center', backgroundColor: T.bg, borderStyle: 'dashed' },
  role: { color: T.mut, fontSize: 9, letterSpacing: 1, marginBottom: 5 }, text: { color: T.txt, fontSize: 14, lineHeight: 20 }, error: { color: T.txt, fontSize: 12, marginTop: 4 },
  composer: { flexDirection: 'row', alignItems: 'flex-end', gap: 8, padding: 10, borderTopWidth: 1, borderColor: T.line },
  input: { flex: 1, maxHeight: 100, minHeight: 42, backgroundColor: T.panel, color: T.txt, borderWidth: 1, borderColor: T.line, borderRadius: 9, padding: 10 },
  send: { minHeight: 42, justifyContent: 'center', paddingHorizontal: 14, borderRadius: 9, backgroundColor: T.node }, sendText: { color: T.nodeTxt, fontWeight: '700' },
});
'''
TERMINAL = r'''import React, { useEffect, useRef, useState } from 'react';
import { ScrollView, StyleSheet, Switch, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { approve, execManual, getPending, getTerminal, reject, setModo } from './api';
import { demoPending, demoTerminal, demoTerminalAction } from './mock';
import { T } from './theme';

const MONO = 'monospace';

export default function Terminal({ mode, url }) {
  const [raw, setRaw] = useState(false);
  const [pending, setPending] = useState([]);
  const [modo, setModoLocal] = useState('manual');
  const [execEnabled, setExecEnabled] = useState(false);
  const [lines, setLines] = useState([]);
  const [command, setCommand] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const cursor = useRef(0);
  const demo = useRef(demoTerminal());

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        if (mode === 'demo') {
          demo.current = demoPending(demo.current);
          if (alive) { setPending(demo.current.pendientes); setModoLocal(demo.current.modo); setExecEnabled(demo.current.exec_habilitado); setLines(demo.current.lineas); }
          return;
        }
        const [log, p] = await Promise.all([getTerminal(url, cursor.current), getPending(url)]);
        if (!alive) return;
        if (Array.isArray(log.lineas) && log.lineas.length) setLines((old) => [...old, ...log.lineas.filter((x) => !old.some((y) => y.n === x.n))]);
        if (Number.isInteger(log.siguiente)) cursor.current = log.siguiente;
        setPending(p.pendientes || []); setModoLocal(p.modo || 'manual'); setExecEnabled(!!p.exec_habilitado); setErr('');
      } catch (e) { if (alive) setErr(String(e.message || e)); }
    };
    tick(); const id = setInterval(tick, 700);
    return () => { alive = false; clearInterval(id); };
  }, [mode, url]);

  const act = async (fn) => { if (busy) return; setBusy(true); setErr(''); try { await fn(); } catch (e) { setErr(String(e.message || e)); } finally { setBusy(false); } };
  const doApprove = (p, edited) => act(async () => {
    if (mode === 'demo') demo.current = demoTerminalAction(demo.current, 'approve', p.id, edited || p.cmd);
    else await approve(url, p.id, edited || undefined);
  });
  const doReject = (p) => act(async () => {
    if (mode === 'demo') demo.current = demoTerminalAction(demo.current, 'reject', p.id, reason);
    else await reject(url, p.id, reason || undefined);
    setReason('');
  });
  const doModo = (next) => act(async () => { if (mode === 'demo') demo.current = { ...demo.current, modo: next }; else await setModo(url, next); setModoLocal(next); });
  const doExec = () => act(async () => { const c = command.trim(); if (!c) return; if (mode === 'demo') demo.current = demoTerminalAction(demo.current, 'exec', null, c); else await execManual(url, c); setCommand(''); });

  return <View style={s.root}>
    <View style={s.top}><Text style={s.title}>Terminal</Text><View style={s.switch}><Text style={s.mut}>Filtrada</Text><Switch value={raw} onValueChange={setRaw} trackColor={{ false: T.line, true: T.line }} thumbColor={T.node} /><Text style={s.mut}>Cruda</Text></View></View>
    {!!err && <Text style={s.error}>⚠ {err}</Text>}
    <ScrollView style={s.log} contentContainerStyle={s.logPad}>
      {lines.map((l, i) => <View key={`${l.n}-${i}`}><Text style={s.line}>{raw && l.crudo ? l.crudo : `[${l.t}] ${l.tipo.toUpperCase()} ${l.texto}`}</Text></View>)}
      {!lines.length && <Text style={s.mut}>Esperando salida…</Text>}
    </ScrollView>
    <View style={s.modeRow}><Text style={s.label}>MODO</Text><TouchableOpacity onPress={() => doModo(modo === 'manual' ? 'auto' : 'manual')} style={s.modeBtn}><Text style={s.text}>{modo}</Text></TouchableOpacity><Text style={s.mut}>{execEnabled ? 'exec habilitado' : 'exec manual desactivada'}</Text></View>
    <ScrollView style={s.queue} contentContainerStyle={{ padding: 10 }}>
      <Text style={s.queueTitle}>APROBACIONES ({pending.length})</Text>
      {pending.map((p) => <Approval key={p.id} p={p} onApprove={doApprove} onReject={doReject} reason={reason} setReason={setReason} />)}
      {!pending.length && <Text style={s.mut}>No hay comandos pendientes.</Text>}
    </ScrollView>
    <View style={s.manual}><TextInput style={[s.input, !execEnabled && s.disabled]} value={command} onChangeText={setCommand} editable={execEnabled} autoCapitalize="none" autoCorrect={false} placeholder={execEnabled ? '$ comando propio…' : 'Servidor no habilitó ejecución manual'} placeholderTextColor={T.mut} /><TouchableOpacity style={[s.run, !execEnabled && s.disabledBtn]} disabled={!execEnabled} onPress={doExec}><Text style={s.runText}>Ejecutar</Text></TouchableOpacity></View>
  </View>;
}

function Approval({ p, onApprove, onReject, reason, setReason }) {
  const [edited, setEdited] = useState(p.cmd);
  return <View style={[s.card, p.riesgo && s.risky]}>
    <Text style={s.label}>{p.riesgo ? '⚠ RIESGO' : 'PROPUESTO'} · paso {p.paso}</Text>
    <TextInput style={s.cmd} value={edited} onChangeText={setEdited} multiline autoCapitalize="none" autoCorrect={false} />
    {!!p.pensamiento && <Text style={s.mut}>{p.pensamiento}</Text>}
    <TextInput style={s.reason} value={reason} onChangeText={setReason} placeholder="Motivo de rechazo (opcional)" placeholderTextColor={T.mut} />
    <View style={s.buttons}><TouchableOpacity style={s.btn} onPress={() => onApprove(p, p.cmd)}><Text style={s.btnText}>Ejecutar</Text></TouchableOpacity><TouchableOpacity style={s.btn} onPress={() => onApprove(p, edited)}><Text style={s.btnText}>Editar y ejecutar</Text></TouchableOpacity><TouchableOpacity style={s.btn} onPress={() => onReject(p)}><Text style={s.btnText}>Rechazar</Text></TouchableOpacity></View>
  </View>;
}

const s = StyleSheet.create({ root: { flex: 1 }, top: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 12, borderBottomWidth: 1, borderColor: T.line }, title: { color: T.txt, fontSize: 16, fontWeight: '700' }, switch: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  log: { flex: 1, minHeight: 120, backgroundColor: '#060607', borderBottomWidth: 1, borderColor: T.line }, logPad: { padding: 10 }, line: { color: T.txt, fontFamily: MONO, fontSize: 11, lineHeight: 17 }, mut: { color: T.mut, fontSize: 11 }, error: { color: T.txt, fontSize: 12, padding: 8 }, modeRow: { flexDirection: 'row', alignItems: 'center', gap: 9, padding: 8, borderBottomWidth: 1, borderColor: T.line }, label: { color: T.mut, fontSize: 9, letterSpacing: 1 }, modeBtn: { borderWidth: 1, borderColor: T.line, borderRadius: 14, paddingVertical: 5, paddingHorizontal: 12 }, text: { color: T.txt, fontSize: 12 }, queue: { maxHeight: 280 }, queueTitle: { color: T.mut, fontSize: 10, letterSpacing: 1, marginBottom: 7 }, card: { borderWidth: 1, borderColor: T.line, backgroundColor: T.panel, borderRadius: 9, padding: 10, marginBottom: 8 }, risky: { borderStyle: 'dashed' }, cmd: { color: T.txt, fontFamily: MONO, fontSize: 12, borderWidth: 1, borderColor: T.line, borderRadius: 7, padding: 8, marginVertical: 7, minHeight: 42 }, reason: { color: T.txt, borderWidth: 1, borderColor: T.line, borderRadius: 7, padding: 7, marginBottom: 7 }, buttons: { flexDirection: 'row', gap: 6, flexWrap: 'wrap' }, btn: { borderWidth: 1, borderColor: T.line, borderRadius: 16, paddingVertical: 7, paddingHorizontal: 10 }, btnText: { color: T.txt, fontSize: 11 }, manual: { flexDirection: 'row', gap: 7, padding: 9, borderTopWidth: 1, borderColor: T.line }, input: { flex: 1, minHeight: 40, color: T.txt, backgroundColor: T.panel, borderWidth: 1, borderColor: T.line, borderRadius: 8, padding: 9 }, disabled: { opacity: 0.45 }, run: { justifyContent: 'center', paddingHorizontal: 12, borderRadius: 8, backgroundColor: T.node }, disabledBtn: { opacity: 0.35 }, runText: { color: T.nodeTxt, fontWeight: '700' },
});
'''
API_ADD = r'''
// ---- Chat + Terminal
export const getTerminal = (base, desde = 0) => j(base, `/terminal?desde=${encodeURIComponent(desde)}`);
export const getPending = (base) => j(base, '/pending');
export const approve = (base, id, cmd) => j(base, '/approve', { method: 'POST', body: JSON.stringify(cmd == null ? { id } : { id, cmd }) });
export const reject = (base, id, motivo) => j(base, '/reject', { method: 'POST', body: JSON.stringify(motivo ? { id, motivo } : { id }) });
export const setModo = (base, modo) => j(base, '/modo', { method: 'POST', body: JSON.stringify({ modo }) });
export const execManual = (base, cmd) => j(base, '/exec', { method: 'POST', body: JSON.stringify({ cmd }) });
export const getChat = (base, desde = 0) => j(base, `/chat?desde=${encodeURIComponent(desde)}`);
export const postChat = (base, texto) => j(base, '/chat', { method: 'POST', body: JSON.stringify({ texto }) });
'''
MOCK_ADD = r'''
// ---- Chat + Terminal demo
export const demoChatInit = () => ({
  mensajes: [
    { n: 1, rol: 'sistema', texto: 'Modo Demo activo. El backend no ejecuta comandos reales.', t: '16:00:00' },
    { n: 2, rol: 'cerebro', texto: 'Listo. Dime qué objetivo quieres conseguir.', t: '16:00:01' },
  ], next: 3, t: 0,
});
export const demoChatTick = (s) => s;
export const demoChatSend = (s, texto) => ({
  ...s,
  mensajes: [...s.mensajes,
    { n: s.next, rol: 'tu', texto, t: '16:00:02' },
    { n: s.next + 1, rol: 'cerebro', texto: 'Entendido. En modo Demo propondría los pasos y pediría aprobación antes de ejecutar.', t: '16:00:03' },
  ], next: s.next + 2,
});

export const demoTerminal = () => ({
  modo: 'manual', exec_habilitado: false, t: 0,
  lineas: [
    { n: 1, t: '16:00:01', tipo: 'info', texto: 'Demo iniciada: terminal simulada.', crudo: null },
    { n: 2, t: '16:00:02', tipo: 'cmd', texto: '$ pwd', crudo: '$ pwd' },
    { n: 3, t: '16:00:02', tipo: 'out', texto: '/data/data/com.termux/files/home/neurotok', crudo: '/data/data/com.termux/files/home/neurotok' },
  ],
  pendientes: [
    { id: 1, cmd: 'python -m py_compile backend/*.py', pensamiento: 'Validar sintaxis antes de continuar.', paso: 1, riesgo: false },
    { id: 2, cmd: 'rm -rf /tmp/demo', pensamiento: 'Ejemplo de comando marcado para revisión humana.', paso: 2, riesgo: true },
    { id: 3, cmd: 'git status --short', pensamiento: 'Comprobar cambios del repositorio.', paso: 3, riesgo: false },
  ],
});
export const demoPending = (s) => ({ ...s, t: s.t + 1 });
export const demoTerminalAction = (s, action, id, value) => {
  if (action === 'approve') return { ...s, pendientes: s.pendientes.filter((p) => p.id !== id), lineas: [...s.lineas, { n: s.lineas.length + 1, t: '16:00:04', tipo: 'cmd', texto: `$ ${value}`, crudo: `$ ${value}` }, { n: s.lineas.length + 2, t: '16:00:04', tipo: 'out', texto: 'exit 0 (Demo)', crudo: 'exit 0 (Demo)' }] };
  if (action === 'reject') return { ...s, pendientes: s.pendientes.filter((p) => p.id !== id), lineas: [...s.lineas, { n: s.lineas.length + 1, t: '16:00:05', tipo: 'info', texto: `Comando ${id} rechazado${value ? `: ${value}` : ''}.`, crudo: null }] };
  if (action === 'exec') return { ...s, lineas: [...s.lineas, { n: s.lineas.length + 1, t: '16:00:06', tipo: 'cmd', texto: `$ ${value}`, crudo: `$ ${value}` }] };
  return s;
};
'''
CONFIRMACION = r'''# Neurotok — Confirmación Tarea 2

## Qué se hizo
- Añadidas las pestañas `Chat` y `Terminal` sin eliminar Lienzo, Bóveda ni Ajustes.
- `Chat`: conversación `tu` / `cerebro` / `sistema`, envío de objetivos y polling mientras la pestaña está abierta.
- `Terminal`: log filtrado/crudo, cola de aprobación editable, Ejecutar / Editar y ejecutar / Rechazar, modo manual/auto y ejecución manual condicionada por `exec_habilitado`.
- Añadidos los endpoints de la API definidos para Chat y Terminal.
- Añadido Demo con conversación simulada y tres comandos pendientes, incluido uno marcado como riesgo.
- Se mantuvo el tema existente: negro mate, grises fríos y sin colores de estado nuevos; el riesgo se marca por texto/forma.

## Qué se probó
- Revisión estática de los archivos generados y de los contratos de endpoints contra `docs/TRASPASO_NEUROTOK.md`.
- Comprobación de que los cambios de `App.js` solo registran las nuevas pestañas/componentes y conservan Lienzo, Bóveda y Ajustes.

## Qué NO se pudo probar
- No se ejecutó Expo Go en un teléfono real desde este entorno.
- No se ejecutó `esbuild`/Metro aquí con las dependencias completas del proyecto.
- No se probó contra un backend real porque la implementación del contrato corresponde a otra tarea.
- No se probó una respuesta HTTP 401/403 real; sí quedó manejo explícito del 401 y de errores de red.

## Supuestos
- El backend implementará exactamente los endpoints y formas indicados en la Tarea 2.
- `Authorization: Bearer <token>` continúa siendo gestionado por `auth` en `api.js`.
- El polling se limita a 700 ms y se detiene al desmontar la pestaña.

## Archivos reservados
No se modificaron `backend/agent_loop.py`, `backend/worker_pool.py` ni `backend/prompt_filter.py`.
No se requiere cambio en ellos para esta tarea.
'''


def blob_sha(text: str) -> str:
    raw = text.encode()
    header = f"blob {len(raw)}\0".encode()
    return hashlib.sha1(header + raw).hexdigest()


def fail(msg: str):
    raise SystemExit(f"[TAREA 2] NO APLICADO: {msg}")


def main():
    files = {k: ROOT / k for k in EXPECTED}
    desired_markers = {
        "app_fuente/App.js": ["import Chat from './src/Chat';", "import Terminal from './src/Terminal';", "const TABS = [['C', 'Chat'], ['T', 'Terminal']"],
        "app_fuente/src/api.js": ["export const getTerminal", "export const getChat"],
        "app_fuente/src/mock.js": ["export const demoChatInit", "export const demoTerminal"],
    }

    # Preflight completo: si algo no coincide, no tocar ningún archivo.
    for rel, path in files.items():
        if not path.exists(): fail(f"falta {rel}")
        text = path.read_text()
        sha = blob_sha(text)
        if sha != EXPECTED[rel] and not all(m in text for m in desired_markers[rel]):
            fail(f"{rel} no coincide con la versión esperada de main (sha {sha}); revisa antes de aplicar")

    for rel in ("app_fuente/src/Chat.js", "app_fuente/src/Terminal.js"):
        path = ROOT / rel
        if path.exists() and path.read_text() not in (CHAT if rel.endswith("Chat.js") else TERMINAL,):
            if path.read_text().strip(): fail(f"{rel} ya existe y no coincide; no se sobrescribe")

    # App.js: registrar imports, pestañas y renderizado.
    app = files["app_fuente/App.js"].read_text()
    if "import Chat from './src/Chat';" not in app:
        old = "import Canvas from './src/Canvas';\n"
        if old not in app: fail("App.js: import Canvas no coincide")
        app = app.replace(old, old + "import Chat from './src/Chat';\nimport Terminal from './src/Terminal';\n", 1)
    if "const TABS = [['C', 'Chat'], ['T', 'Terminal']" not in app:
        old = "const TABS = [['L', 'Lienzo'], ['B', 'Bóveda'], ['S', 'Ajustes']];"
        new = "const TABS = [['C', 'Chat'], ['T', 'Terminal'], ['L', 'Lienzo'], ['B', 'Bóveda'], ['S', 'Ajustes']];"
        if old not in app: fail("App.js: TABS no coincide")
        app = app.replace(old, new, 1)
    if "{tab === 'C' && <Chat mode={mode} url={url} />}" not in app:
        old = "        {tab === 'L' && <Lienzo snap={snap} />}\n"
        new = "        {tab === 'C' && <Chat mode={mode} url={url} />}\n        {tab === 'T' && <Terminal mode={mode} url={url} />}\n" + old
        if old not in app: fail("App.js: bloque de pestañas no coincide")
        app = app.replace(old, new, 1)

    writes = []
    if blob_sha(files["app_fuente/App.js"].read_text()) != blob_sha(app): writes.append((files["app_fuente/App.js"], app))

    api = files["app_fuente/src/api.js"].read_text()
    if "export const getTerminal" not in api:
        api += API_ADD
        writes.append((files["app_fuente/src/api.js"], api))

    mock = files["app_fuente/src/mock.js"].read_text()
    if "export const demoChatInit" not in mock:
        mock += MOCK_ADD
        writes.append((files["app_fuente/src/mock.js"], mock))

    chat_path = ROOT / "app_fuente/src/Chat.js"
    if not chat_path.exists(): writes.append((chat_path, CHAT))
    term_path = ROOT / "app_fuente/src/Terminal.js"
    if not term_path.exists(): writes.append((term_path, TERMINAL))

    for path, content in writes:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    (ROOT / "CONFIRMACION_TAREA_2.md").write_text(CONFIRMACION)
    print(f"[TAREA 2] Aplicado correctamente: {len(writes)} archivo(s) modificado(s)/creado(s).")
    print("[TAREA 2] Revisa con git diff y ejecuta las pruebas del bloque de Termux.")

if __name__ == "__main__":
    main()
