#!/usr/bin/env python3
"""Tarea 2 · pestañas Chat y Terminal con aprobación de comandos (rama feat/chat-ui).

Uso, desde la raíz del repo (~/neurotok):
    python fase_2.py            aplica los cambios (idempotente)
    python fase_2.py probar     comprueba sintaxis JSX (esbuild) y corre las pruebas de lógica (node)

Si algo no coincide con lo esperado, NO toca ningún archivo y lo dice.
Archivos que toca: app_fuente/App.js (mínimo), src/api.js y src/mock.js (se les añade al final),
y crea src/Chat.js y src/Terminal.js. No toca backend/ ni ningún archivo reservado.
"""
import os
import shutil
import subprocess
import sys
import tempfile

APP = 'app_fuente'
RUTAS = {k: os.path.join(APP, v) for k, v in {
    'app': 'App.js', 'api': 'src/api.js', 'mock': 'src/mock.js', 'chat': 'src/Chat.js', 'term': 'src/Terminal.js'}.items()}
MARCA = 'NEUROTOK-TAREA2'

API_ADD = r'''
// ---- Chat y Terminal (Tarea 2): mismo contrato que el backend, con errores legibles
const jx = async (base, path, opts = {}) => {
  let r;
  try { r = await fetch(base + path, { ...opts, headers: headers() }); }
  catch (e) { throw new Error('Sin conexión con el servidor (¿está corriendo el backend en Termux?)'); }
  if (r.status === 401) throw new Error('Token incorrecto: revisa Ajustes');
  const raw = await r.text();
  let body = {};
  try { body = raw ? JSON.parse(raw) : {}; } catch (e) { body = {}; }
  if (!r.ok) throw new Error(body && body.error ? String(body.error) : `${path}: HTTP ${r.status}`);
  return body;
};
const post = (base, path, body) => jx(base, path, { method: 'POST', body: JSON.stringify(body || {}) });

// Misma forma que demoApi (mock.js): las pantallas Chat y Terminal eligen una u otra
export const liveApi = (base) => ({
  terminal: (desde = 0) => jx(base, `/terminal?desde=${desde}`),
  pending: () => jx(base, '/pending'),
  approve: (id, cmd) => post(base, '/approve', cmd === undefined ? { id } : { id, cmd }),
  reject: (id, motivo) => post(base, '/reject', motivo ? { id, motivo } : { id }),
  modo: (modo) => post(base, '/modo', { modo }),
  exec: (cmd) => post(base, '/exec', { cmd }),
  chat: (desde = 0) => jx(base, `/chat?desde=${desde}`),
  chatPost: (texto) => post(base, '/chat', { texto }),
});
'''
MOCK_ADD = r'''
// ---- Chat y Terminal simuladas (Tarea 2): misma forma que el contrato de la API
const D = { term: [], chat: [], pend: [], modo: 'manual', id: 1, seeded: false };
const hora = () => new Date().toTimeString().slice(0, 8);
const tl = (tipo, texto, crudo = null) => { D.term.push({ n: D.term.length, t: hora(), tipo, texto, crudo }); };
const cm = (rol, texto) => { D.chat.push({ n: D.chat.length, rol, texto, t: hora() }); };
const enqueue = (cmd, pensamiento, paso, riesgo = false) => { D.pend.push({ id: D.id++, cmd, pensamiento, paso, riesgo }); };

export function demoReset() {
  D.term = []; D.chat = []; D.pend = []; D.modo = 'manual'; D.id = 1; D.seeded = false;
}

function seed() {
  if (D.seeded) return;
  D.seeded = true;
  tl('info', 'Sesión de demostración: nada de esto se ejecuta de verdad.');
  cm('sistema', 'Modo Demo: todo es simulado.');
  cm('cerebro', 'Hola. Dime un objetivo y te propongo los comandos para cumplirlo.');
  cm('tu', 'Crea hola.py que imprima Neurotok y ejecútalo');
  cm('cerebro', 'Entendido. Son 3 pasos. Revisa la pestaña Terminal: ahí te pido aprobación para cada comando.');
  enqueue('pkg install -y python', 'Necesito Python instalado para poder ejecutar el script.', 1);
  enqueue("printf 'print(\"Neurotok\")\\n' > hola.py", 'Creo hola.py con una sola línea.', 2);
  enqueue('rm -rf ~/proyectos_ia/viejo', 'Limpio una carpeta antigua que estorba antes de seguir.', 3, true);
}

function ejecutar(cmd) {
  tl('cmd', cmd);
  if (/^pkg install/.test(cmd)) {
    tl('out', 'python ya está instalado (3.12.7)',
      'Reading package lists... Done\nBuilding dependency tree... Done\npython is already the newest version (3.12.7).\n0 upgraded, 0 newly installed, 0 to remove.');
  } else if (/^python3? hola\.py/.test(cmd)) {
    tl('out', 'Neurotok');
  } else if (/^echo /.test(cmd)) {
    tl('out', cmd.slice(5).replace(/^["']|["']$/g, ''));
  } else if (/^ls\b/.test(cmd)) {
    tl('out', 'hola.py', '-rw------- 1 u0_a217 u0_a217 22 Oct  3 17:20 hola.py\ntotal 4');
  } else if (/^(rm|printf|mkdir|cat)\b/.test(cmd)) {
    tl('out', '(sin salida)', '');
  } else {
    tl('err', 'demo: este comando no está simulado', `bash: ${cmd.split(' ')[0]}: simulado`);
  }
}

function cerrarCola() {
  if (!D.pend.length) cm('cerebro', 'Listo: la cola está vacía. Cuéntame el siguiente objetivo.');
}

export const demoApi = {
  terminal: async (desde = 0) => { seed(); return { siguiente: D.term.length, lineas: D.term.slice(desde) }; },
  pending: async () => {
    seed();
    if (D.modo === 'auto') { // en auto, lo que tiene riesgo sigue esperando a una persona
      const i = D.pend.findIndex((p) => !p.riesgo);
      if (i >= 0) {
        const [p] = D.pend.splice(i, 1);
        ejecutar(p.cmd);
        cm('sistema', `Auto: ejecutado ${p.cmd}`);
        cerrarCola();
      }
    }
    return { modo: D.modo, exec_habilitado: true, pendientes: D.pend.map((p) => ({ ...p })) };
  },
  approve: async (id, cmd) => {
    const i = D.pend.findIndex((p) => p.id === id);
    if (i < 0) throw new Error('Ese comando ya no está pendiente');
    const [p] = D.pend.splice(i, 1);
    const final = cmd !== undefined ? cmd : p.cmd;
    if (cmd !== undefined && cmd !== p.cmd) tl('info', 'Comando editado por ti antes de ejecutarlo');
    ejecutar(final);
    cm('sistema', `Ejecutado (paso ${p.paso}): ${final}`);
    cerrarCola();
    return { ok: true };
  },
  reject: async (id, motivo) => {
    const i = D.pend.findIndex((p) => p.id === id);
    if (i < 0) throw new Error('Ese comando ya no está pendiente');
    const [p] = D.pend.splice(i, 1);
    tl('info', `Rechazado: ${p.cmd}${motivo ? ` — ${motivo}` : ''}`);
    cm('sistema', `Rechazaste: ${p.cmd}${motivo ? ` (${motivo})` : ''}`);
    if (!D.pend.length) {
      cm('cerebro', 'Entendido, no lo ejecuto. Pruebo otro camino.');
      enqueue('ls -la ~/proyectos_ia', 'Antes de tocar nada, miro qué hay en la carpeta.', p.paso);
    }
    return { ok: true };
  },
  modo: async (modo) => {
    if (modo !== 'manual' && modo !== 'auto') throw new Error('modo inválido');
    D.modo = modo;
    tl('info', `Modo de aprobación: ${modo}`);
    return { ok: true };
  },
  exec: async (cmd) => { ejecutar(cmd); return { ok: true }; },
  chat: async (desde = 0) => { seed(); return { siguiente: D.chat.length, mensajes: D.chat.slice(desde) }; },
  chatPost: async (texto) => {
    seed();
    cm('tu', texto);
    cm('cerebro', `Objetivo recibido: "${texto}". Te propongo el primer comando en la Terminal.`);
    setTimeout(() => enqueue('ls -la ~/proyectos_ia', 'Empiezo viendo el estado de la carpeta de proyectos.', 1), 1200);
    return { ok: true };
  },
};
'''
CHAT_JS = r'''// NEUROTOK-TAREA2: pestaña Chat con el cerebro. Archivo generado por fase_2.py.
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { demoApi } from './mock';
import { liveApi } from './api';
import { T } from './theme';

const POLL_MS = 800;
const MAX_MSGS = 500;

function Burbuja({ m }) {
  if (m.rol === 'sistema') return <Text style={s.sys}>{m.texto}</Text>;
  const mio = m.rol === 'tu';
  return (
    <View style={[s.fila, mio ? s.filaTu : s.filaCer]}>
      <View style={[s.bub, mio ? s.bubTu : s.bubCer]}>
        <Text style={mio ? s.txtTu : s.txt}>{m.texto}</Text>
        {!!m.t && <Text style={[s.ts, mio && { color: T.nodeSub }]}>{m.t}</Text>}
      </View>
    </View>
  );
}

export default function Chat({ mode, url, status }) {
  const svc = useMemo(() => (mode === 'demo' ? demoApi : liveApi(url)), [mode, url]);
  const [msgs, setMsgs] = useState([]);
  const [err, setErr] = useState('');
  const [note, setNote] = useState('');
  const [txt, setTxt] = useState('');
  const [sending, setSending] = useState(false);
  const cursor = useRef(0);
  const alive = useRef(true);
  const inflight = useRef(false);
  const stick = useRef(true);
  const scroller = useRef(null);

  const estado = status && status.estado;
  const running = estado === 'EJECUTANDO' || estado === 'PLANIFICANDO';

  const refresh = useCallback(async () => {
    if (inflight.current) return;
    inflight.current = true;
    try {
      const d = await svc.chat(cursor.current);
      if (!alive.current) return;
      if (typeof d.siguiente === 'number' && d.siguiente < cursor.current) { // el servidor se reinició: empezar de cero
        cursor.current = 0; setMsgs([]); return;
      }
      const nuevos = Array.isArray(d.mensajes) ? d.mensajes : [];
      if (nuevos.length) setMsgs((prev) => prev.concat(nuevos).slice(-MAX_MSGS));
      if (typeof d.siguiente === 'number') cursor.current = d.siguiente;
      setErr('');
    } catch (e) {
      if (alive.current) setErr(String(e.message || e));
    } finally { inflight.current = false; }
  }, [svc]);

  // Solo consulta mientras esta pestaña está abierta (App la desmonta al cambiar de pestaña)
  useEffect(() => {
    alive.current = true; cursor.current = 0; setMsgs([]);
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => { alive.current = false; clearInterval(id); };
  }, [refresh]);

  const enviar = async () => {
    const texto = txt.trim();
    if (!texto || sending) return;
    setSending(true);
    try { await svc.chatPost(texto); setTxt(''); setNote(''); stick.current = true; }
    catch (e) { setNote(String(e.message || e)); }
    finally { setSending(false); }
    refresh();
  };

  const onScroll = (e) => {
    const { contentOffset, contentSize, layoutMeasurement } = e.nativeEvent;
    stick.current = contentOffset.y + layoutMeasurement.height >= contentSize.height - 40;
  };

  const msg = note || err;
  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={s.strip}>
        {running
          ? <Text style={s.mut}><Text style={{ color: T.violet }}>● </Text>Tarea en curso · paso {status.paso_actual}/{status.total_pasos}</Text>
          : <Text style={s.mut}>Sin tarea en curso · tu próximo mensaje será un objetivo nuevo</Text>}
      </View>
      {!!msg && <Text style={s.warn}>⚠ {msg}</Text>}
      <ScrollView ref={scroller} style={{ flex: 1 }} contentContainerStyle={s.lista} onScroll={onScroll} scrollEventThrottle={100}
        keyboardShouldPersistTaps="handled"
        onContentSizeChange={() => { if (stick.current && scroller.current) scroller.current.scrollToEnd({ animated: false }); }}>
        {!msgs.length && <Text style={[s.mut, { textAlign: 'center', marginTop: 24 }]}>
          {err ? 'Sin conexión con el cerebro' : 'Escribe un objetivo para empezar'}</Text>}
        {msgs.map((m, i) => <Burbuja key={`${m.n}-${i}`} m={m} />)}
      </ScrollView>
      <View style={s.entrada}>
        <TextInput style={s.input} value={txt} onChangeText={setTxt} multiline editable={!sending}
          placeholder={running ? 'Escribe al cerebro…' : 'Escribe un objetivo…'} placeholderTextColor={T.mut} />
        <TouchableOpacity style={[s.pill, (!txt.trim() || sending) && s.off]} onPress={enviar} disabled={!txt.trim() || sending}>
          <Text style={[s.pillT, { color: T.nodeTxt }]}>Enviar</Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  strip: { paddingHorizontal: 16, paddingVertical: 8, borderBottomWidth: 1, borderColor: T.line },
  mut: { color: T.mut, fontSize: 12 },
  warn: { color: T.txt, fontSize: 12, paddingHorizontal: 14, paddingVertical: 6 },
  lista: { padding: 12, paddingBottom: 16 },
  fila: { flexDirection: 'row', marginBottom: 8 },
  filaTu: { justifyContent: 'flex-end' },
  filaCer: { justifyContent: 'flex-start' },
  bub: { maxWidth: '84%', borderRadius: 14, paddingHorizontal: 12, paddingVertical: 8, borderWidth: 1 },
  bubTu: { backgroundColor: T.node, borderColor: T.node, borderBottomRightRadius: 4 },
  bubCer: { backgroundColor: T.panel, borderColor: T.line, borderBottomLeftRadius: 4 },
  txt: { color: T.txt, fontSize: 14 },
  txtTu: { color: T.nodeTxt, fontSize: 14 },
  ts: { color: T.mut, fontSize: 10, marginTop: 3, alignSelf: 'flex-end' },
  sys: { color: T.mut, fontSize: 12, fontStyle: 'italic', textAlign: 'center', marginVertical: 6, paddingHorizontal: 12 },
  entrada: { flexDirection: 'row', alignItems: 'flex-end', gap: 8, padding: 10, borderTopWidth: 1, borderColor: T.line },
  input: { flex: 1, maxHeight: 110, backgroundColor: T.bg, color: T.txt, borderRadius: 12, borderWidth: 1, borderColor: T.line,
    paddingHorizontal: 12, paddingVertical: 8, fontSize: 14 },
  pill: { backgroundColor: T.node, borderRadius: 18, paddingVertical: 10, paddingHorizontal: 16 },
  pillT: { fontSize: 13, fontWeight: '600' },
  off: { opacity: 0.4 },
});
'''
TERM_JS = r'''// NEUROTOK-TAREA2: pestaña Terminal (log en vivo + cola de aprobación). Archivo generado por fase_2.py.
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { demoApi } from './mock';
import { liveApi } from './api';
import { T } from './theme';

const MONO = Platform.OS === 'ios' ? 'Menlo' : 'monospace';
const MAX_LINEAS = 1500;
const POLL_MS = 800;

const Pill = ({ children, onPress, on, disabled }) => (
  <TouchableOpacity style={[s.pill, on && s.pillOn, disabled && s.off]} onPress={onPress} disabled={disabled}>
    <Text style={[s.pillT, on && { color: T.nodeTxt }]}>{children}</Text>
  </TouchableOpacity>
);

const Seg = ({ items, value, onChange }) => (
  <View style={s.seg}>
    {items.map(([k, label]) => (
      <TouchableOpacity key={k} style={[s.segItem, value === k && s.segOn]} onPress={() => onChange(k)}>
        <Text style={[s.segT, value === k && { color: T.nodeTxt }]}>{label}</Text>
      </TouchableOpacity>
    ))}
  </View>
);

// Tarjeta de un comando propuesto: editable, con tres acciones
function Pendiente({ p, busy, onApprove, onReject }) {
  const [txt, setTxt] = useState(p.cmd);
  const [rechazando, setRechazando] = useState(false);
  const [motivo, setMotivo] = useState('');
  const [armado, setArmado] = useState(false); // comandos de riesgo: se pide un segundo toque
  const editado = txt !== p.cmd;
  const vacio = txt.trim() === '';
  const lanzar = (cmd) => {
    if (p.riesgo && !armado) { setArmado(true); return; }
    onApprove(p.id, cmd);
  };
  return (
    <View style={s.card}>
      <Text style={s.label}>PASO {p.paso}</Text>
      {p.riesgo && <Text style={s.riskTag}>⚠ RIESGO · REVÍSALO ANTES DE EJECUTAR</Text>}
      {!!p.pensamiento && <Text style={[s.mut, { marginBottom: 6 }]}>{p.pensamiento}</Text>}
      <TextInput style={s.cmdInput} value={txt} onChangeText={(v) => { setTxt(v); setArmado(false); }} multiline
        autoCapitalize="none" autoCorrect={false} editable={!busy} />
      {!rechazando ? (
        <View style={s.row}>
          <Pill on disabled={busy} onPress={() => lanzar(undefined)}>
            {p.riesgo && armado ? '¿Seguro? Toca otra vez' : editado ? 'Ejecutar original' : 'Ejecutar'}
          </Pill>
          <Pill disabled={busy || vacio} onPress={() => lanzar(txt)}>Editar y ejecutar</Pill>
          <Pill disabled={busy} onPress={() => setRechazando(true)}>Rechazar</Pill>
        </View>
      ) : (
        <View>
          <TextInput style={s.input} value={motivo} onChangeText={setMotivo} placeholder="Motivo (opcional)"
            placeholderTextColor={T.mut} editable={!busy} />
          <View style={s.row}>
            <Pill on disabled={busy} onPress={() => onReject(p.id, motivo.trim())}>Confirmar rechazo</Pill>
            <Pill disabled={busy} onPress={() => setRechazando(false)}>Cancelar</Pill>
          </View>
        </View>
      )}
    </View>
  );
}

const fmt = (l, cruda) => {
  const base = cruda && l.crudo ? l.crudo : l.texto;
  if (l.tipo === 'cmd') return `${l.t ? `${l.t} ` : ''}$ ${base}`;
  if (l.tipo === 'err') return `✖ ${base}`;
  if (l.tipo === 'info') return `· ${base}`;
  return base;
};
const ESTILO = {
  cmd: { color: '#ffffff', fontWeight: 'bold' },
  out: { color: T.txt },
  err: { color: T.txt, fontStyle: 'italic', fontWeight: '700' },
  info: { color: T.mut },
};

export default function Terminal({ mode, url }) {
  const svc = useMemo(() => (mode === 'demo' ? demoApi : liveApi(url)), [mode, url]);
  const [lineas, setLineas] = useState([]);
  const [pend, setPend] = useState({ modo: 'manual', exec_habilitado: false, pendientes: [] });
  const [err, setErr] = useState('');
  const [note, setNote] = useState('');
  const [cruda, setCruda] = useState(false);
  const [busy, setBusy] = useState({});
  const [cmdTxt, setCmdTxt] = useState('');
  const [sending, setSending] = useState(false);
  const cursor = useRef(0);
  const alive = useRef(true);
  const inflight = useRef(false);
  const stick = useRef(true);
  const scroller = useRef(null);

  const refresh = useCallback(async () => {
    if (inflight.current) return;
    inflight.current = true;
    try {
      const [t, p] = await Promise.all([svc.terminal(cursor.current), svc.pending()]);
      if (!alive.current) return;
      if (typeof t.siguiente === 'number' && t.siguiente < cursor.current) { // el servidor se reinició: empezar de cero
        cursor.current = 0; setLineas([]); return;
      }
      const nuevas = Array.isArray(t.lineas) ? t.lineas : [];
      if (nuevas.length) setLineas((prev) => prev.concat(nuevas).slice(-MAX_LINEAS));
      if (typeof t.siguiente === 'number') cursor.current = t.siguiente;
      setPend({ modo: p.modo === 'auto' ? 'auto' : 'manual', exec_habilitado: p.exec_habilitado === true,
        pendientes: Array.isArray(p.pendientes) ? p.pendientes : [] });
      setErr('');
    } catch (e) {
      if (alive.current) setErr(String(e.message || e));
    } finally { inflight.current = false; }
  }, [svc]);

  // Solo consulta mientras esta pestaña está abierta (App la desmonta al cambiar de pestaña)
  useEffect(() => {
    alive.current = true; cursor.current = 0; setLineas([]);
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => { alive.current = false; clearInterval(id); };
  }, [refresh]);

  const act = async (id, fn) => {
    setBusy((b) => ({ ...b, [id]: true }));
    try { await fn(); setNote(''); } catch (e) { setNote(String(e.message || e)); }
    finally { setBusy((b) => { const n = { ...b }; delete n[id]; return n; }); }
    refresh();
  };
  const approve = (id, cmd) => act(id, () => svc.approve(id, cmd));
  const reject = (id, motivo) => act(id, () => svc.reject(id, motivo));

  const cambiarModo = async (m) => {
    if (m === pend.modo) return;
    setPend((p) => ({ ...p, modo: m }));
    try { await svc.modo(m); setNote(''); } catch (e) { setNote(String(e.message || e)); }
    refresh();
  };

  const enviar = async () => {
    const c = cmdTxt.trim();
    if (!c || sending || !pend.exec_habilitado) return;
    setSending(true);
    try { await svc.exec(c); setCmdTxt(''); setNote(''); stick.current = true; }
    catch (e) { setNote(String(e.message || e)); }
    finally { setSending(false); }
    refresh();
  };

  const onScroll = (e) => {
    const { contentOffset, contentSize, layoutMeasurement } = e.nativeEvent;
    stick.current = contentOffset.y + layoutMeasurement.height >= contentSize.height - 40;
  };

  const msg = note || err;
  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={s.bar}>
        <View style={{ flex: 1 }}>
          <Text style={s.label}>APROBACIÓN</Text>
          <Seg items={[['manual', 'Manual'], ['auto', 'Auto']]} value={pend.modo} onChange={cambiarModo} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={s.label}>VISTA</Text>
          <Seg items={[['f', 'Filtrada'], ['c', 'Cruda']]} value={cruda ? 'c' : 'f'} onChange={(k) => setCruda(k === 'c')} />
        </View>
      </View>
      {!!msg && <Text style={s.warn}>⚠ {msg}</Text>}
      {pend.pendientes.length > 0 && (
        <View style={s.queue}>
          <Text style={[s.label, { paddingHorizontal: 12, paddingTop: 8 }]}>POR APROBAR ({pend.pendientes.length})</Text>
          <ScrollView contentContainerStyle={{ padding: 10, paddingTop: 4 }} keyboardShouldPersistTaps="handled" nestedScrollEnabled>
            {pend.pendientes.map((p) => (
              <Pendiente key={p.id} p={p} busy={!!busy[p.id]} onApprove={approve} onReject={reject} />
            ))}
          </ScrollView>
        </View>
      )}
      <ScrollView ref={scroller} style={s.log} contentContainerStyle={{ padding: 10 }} onScroll={onScroll} scrollEventThrottle={100}
        onContentSizeChange={() => { if (stick.current && scroller.current) scroller.current.scrollToEnd({ animated: false }); }}>
        {!lineas.length && <Text style={s.mut}>{err ? 'Sin conexión con la terminal' : 'Esperando salida…'}</Text>}
        {lineas.map((l) => <Text key={l.n} style={[s.mono, ESTILO[l.tipo] || ESTILO.out]}>{fmt(l, cruda)}</Text>)}
      </ScrollView>
      <View style={s.execRow}>
        <TextInput style={[s.input, { flex: 1, marginTop: 0 }, !pend.exec_habilitado && s.off]} value={cmdTxt} onChangeText={setCmdTxt}
          editable={pend.exec_habilitado && !sending} onSubmitEditing={enviar} returnKeyType="send" blurOnSubmit={false}
          placeholder={pend.exec_habilitado ? '$ escribe un comando' : 'Terminal manual desactivada en el servidor'}
          placeholderTextColor={T.mut} autoCapitalize="none" autoCorrect={false} />
        <Pill on onPress={enviar} disabled={!pend.exec_habilitado || sending || !cmdTxt.trim()}>Enviar</Pill>
      </View>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  bar: { flexDirection: 'row', gap: 10, paddingHorizontal: 12, paddingTop: 10 },
  label: { color: T.mut, fontSize: 10, letterSpacing: 1, marginBottom: 4 },
  mut: { color: T.mut, fontSize: 12 },
  warn: { color: T.txt, fontSize: 12, paddingHorizontal: 14, paddingVertical: 6 },
  seg: { flexDirection: 'row', borderWidth: 1, borderColor: T.line, borderRadius: 10, overflow: 'hidden', marginBottom: 8 },
  segItem: { flex: 1, alignItems: 'center', paddingVertical: 8 },
  segOn: { backgroundColor: T.node },
  segT: { color: T.mut, fontSize: 12, fontWeight: '600', letterSpacing: 0.5 },
  queue: { maxHeight: '48%', borderTopWidth: 1, borderBottomWidth: 1, borderColor: T.line },
  card: { backgroundColor: T.panel, borderRadius: 10, padding: 12, marginBottom: 8, borderWidth: 1, borderColor: T.violet },
  riskTag: { alignSelf: 'flex-start', backgroundColor: T.node, color: T.nodeTxt, fontSize: 11, fontWeight: '800', letterSpacing: 0.5,
    paddingHorizontal: 8, paddingVertical: 3, borderRadius: 4, marginBottom: 6, overflow: 'hidden' },
  cmdInput: { backgroundColor: '#060607', color: T.txt, fontFamily: MONO, fontSize: 13, borderRadius: 8, borderWidth: 1,
    borderColor: T.line, padding: 10, marginBottom: 10 },
  input: { backgroundColor: T.bg, color: T.txt, borderRadius: 8, borderWidth: 1, borderColor: T.line, padding: 10, marginTop: 4, marginBottom: 8 },
  row: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  pill: { borderWidth: 1, borderColor: T.line, borderRadius: 18, paddingVertical: 8, paddingHorizontal: 14 },
  pillOn: { backgroundColor: T.node, borderColor: T.node },
  pillT: { color: T.txt, fontSize: 13 },
  off: { opacity: 0.4 },
  log: { flex: 1, backgroundColor: '#060607' },
  mono: { fontFamily: MONO, fontSize: 12, lineHeight: 17 },
  execRow: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10, borderTopWidth: 1, borderColor: T.line },
});
'''
PRUEBA_MJS = r'''// Prueba de la lógica de Demo y del cliente de la API (sin React). Se ejecuta con node.
import assert from 'node:assert/strict';
import { demoApi, demoReset } from './mock.mjs';
import { auth, liveApi } from './api.mjs';

let ok = 0;
const t = async (nombre, fn) => { await fn(); ok += 1; console.log('  ok  ' + nombre); };

// ---- Demo
demoReset();
await t('demo: arranca con 3 pendientes y uno de riesgo', async () => {
  const p = await demoApi.pending();
  assert.equal(p.modo, 'manual');
  assert.equal(p.exec_habilitado, true);
  assert.equal(p.pendientes.length, 3);
  assert.equal(p.pendientes.filter((x) => x.riesgo).length, 1);
  for (const x of p.pendientes) assert.ok(x.id && x.cmd && typeof x.pensamiento === 'string' && x.paso);
});
await t('demo: terminal y chat respetan desde/siguiente', async () => {
  const a = await demoApi.terminal(0);
  assert.equal(a.siguiente, a.lineas.length);
  const b = await demoApi.terminal(a.siguiente);
  assert.equal(b.lineas.length, 0);
  const c = await demoApi.chat(0);
  assert.ok(c.mensajes.some((m) => m.rol === 'tu') && c.mensajes.some((m) => m.rol === 'cerebro') && c.mensajes.some((m) => m.rol === 'sistema'));
});
await t('demo: aprobar el original ejecuta y quita de la cola', async () => {
  const [p1] = (await demoApi.pending()).pendientes;
  const antes = (await demoApi.terminal(0)).siguiente;
  await demoApi.approve(p1.id);
  const d = await demoApi.terminal(antes);
  assert.equal(d.lineas[0].tipo, 'cmd');
  assert.equal(d.lineas[0].texto, p1.cmd);
  assert.ok(d.lineas.some((l) => l.tipo === 'out' && l.crudo));        // la vista cruda tiene más detalle
  assert.equal((await demoApi.pending()).pendientes.length, 2);
});
await t('demo: aprobar con texto editado ejecuta el editado', async () => {
  const [p2] = (await demoApi.pending()).pendientes;
  const antes = (await demoApi.terminal(0)).siguiente;
  await demoApi.approve(p2.id, 'echo editado');
  const d = await demoApi.terminal(antes);
  assert.ok(d.lineas.some((l) => l.tipo === 'cmd' && l.texto === 'echo editado'));
  assert.ok(d.lineas.some((l) => l.tipo === 'out' && l.texto === 'editado'));
});
await t('demo: rechazar con motivo deja rastro y el cerebro propone otro', async () => {
  const [p3] = (await demoApi.pending()).pendientes;
  assert.equal(p3.riesgo, true);
  await demoApi.reject(p3.id, 'borra datos');
  const log = (await demoApi.terminal(0)).lineas.map((l) => l.texto).join('\n');
  assert.match(log, /Rechazado: rm -rf .* — borra datos/);
  const p = await demoApi.pending();
  assert.equal(p.pendientes.length, 1);
  assert.equal(p.pendientes[0].riesgo, false);
});
await t('demo: aprobar un id inexistente da error claro', async () => {
  await assert.rejects(() => demoApi.approve(9999), /ya no está pendiente/);
  await assert.rejects(() => demoApi.reject(9999), /ya no está pendiente/);
});
await t('demo: modo auto ejecuta lo seguro y deja el riesgo esperando', async () => {
  demoReset();
  await demoApi.pending();
  await demoApi.modo('auto');
  let p = await demoApi.pending(); p = await demoApi.pending(); p = await demoApi.pending();
  assert.equal(p.modo, 'auto');
  assert.equal(p.pendientes.length, 1);
  assert.equal(p.pendientes[0].riesgo, true);
  await demoApi.modo('manual');
  await assert.rejects(() => demoApi.modo('otro'), /modo inválido/);
});
await t('demo: exec y chatPost generan líneas/mensajes con n creciente', async () => {
  const n0 = (await demoApi.terminal(0)).siguiente;
  await demoApi.exec('echo hola');
  const d = await demoApi.terminal(n0);
  assert.deepEqual(d.lineas.map((l) => l.n), [n0, n0 + 1]);
  const m0 = (await demoApi.chat(0)).siguiente;
  await demoApi.chatPost('hacer algo');
  const c = await demoApi.chat(m0);
  assert.deepEqual(c.mensajes.map((m) => m.rol), ['tu', 'cerebro']);
});

// ---- Cliente real, con fetch simulado
const llamadas = [];
const falso = (status, cuerpo) => async (u, o) => {
  llamadas.push({ u, o });
  return { status, ok: status >= 200 && status < 300, text: async () => (cuerpo === undefined ? '' : (typeof cuerpo === 'string' ? cuerpo : JSON.stringify(cuerpo))) };
};
auth.token = 'TOK';
const api = liveApi('http://127.0.0.1:8000');
await t('api: GET /terminal?desde=N con Bearer', async () => {
  globalThis.fetch = falso(200, { siguiente: 0, lineas: [] });
  await api.terminal(7);
  const l = llamadas.at(-1);
  assert.equal(l.u, 'http://127.0.0.1:8000/terminal?desde=7');
  assert.equal(l.o.headers.Authorization, 'Bearer TOK');
});
await t('api: /approve manda cmd solo si hay versión editada', async () => {
  globalThis.fetch = falso(200, { ok: true });
  await api.approve(3);
  assert.deepEqual(JSON.parse(llamadas.at(-1).o.body), { id: 3 });
  await api.approve(3, 'ls -la');
  assert.deepEqual(JSON.parse(llamadas.at(-1).o.body), { id: 3, cmd: 'ls -la' });
  assert.equal(llamadas.at(-1).o.method, 'POST');
});
await t('api: /reject, /modo, /exec y /chat con el cuerpo del contrato', async () => {
  globalThis.fetch = falso(200, { ok: true });
  await api.reject(4, 'no'); assert.deepEqual(JSON.parse(llamadas.at(-1).o.body), { id: 4, motivo: 'no' });
  await api.reject(4); assert.deepEqual(JSON.parse(llamadas.at(-1).o.body), { id: 4 });
  await api.modo('auto'); assert.deepEqual(JSON.parse(llamadas.at(-1).o.body), { modo: 'auto' });
  await api.exec('pwd'); assert.deepEqual(JSON.parse(llamadas.at(-1).o.body), { cmd: 'pwd' });
  await api.chatPost('hola'); assert.deepEqual(JSON.parse(llamadas.at(-1).o.body), { texto: 'hola' });
  await api.chat(2); assert.equal(llamadas.at(-1).u, 'http://127.0.0.1:8000/chat?desde=2');
  await api.pending(); assert.equal(llamadas.at(-1).u, 'http://127.0.0.1:8000/pending');
});
await t('api: 403 de /exec muestra el mensaje del servidor', async () => {
  globalThis.fetch = falso(403, { error: 'terminal manual desactivada' });
  await assert.rejects(() => api.exec('ls'), /terminal manual desactivada/);
});
await t('api: 401 pide revisar el token', async () => {
  globalThis.fetch = falso(401, { error: 'x' });
  await assert.rejects(() => api.pending(), /Token incorrecto: revisa Ajustes/);
});
await t('api: sin red da un mensaje claro', async () => {
  globalThis.fetch = async () => { throw new TypeError('Network request failed'); };
  await assert.rejects(() => api.chat(0), /Sin conexión con el servidor/);
});
await t('api: error sin JSON cae a HTTP <código>; respuesta vacía no rompe', async () => {
  globalThis.fetch = falso(500, 'boom');
  await assert.rejects(() => api.pending(), /\/pending: HTTP 500/);
  globalThis.fetch = falso(200, undefined);
  assert.deepEqual(await api.modo('manual'), {});
});

console.log(`\n${ok} pruebas OK`);
process.exit(0);
'''

APP_EDITS = [
    ("import Canvas from './src/Canvas';\n",
     "import Canvas from './src/Canvas';\nimport Chat from './src/Chat';\nimport Terminal from './src/Terminal';\n"),
    ("const TABS = [['L', 'Lienzo'], ['B', 'Bóveda'], ['S', 'Ajustes']];",
     "const TABS = [['C', 'Chat'], ['T', 'Terminal'], ['L', 'Lienzo'], ['B', 'Bóveda'], ['S', 'Ajustes']];"),
    ("const [tab, setTab] = useState('L');",
     "const [tab, setTab] = useState('C');"),
    ("        {tab === 'L' && <Lienzo snap={snap} />}\n",
     "        {tab === 'C' && <Chat mode={mode} url={url} status={snap.status} />}\n"
     "        {tab === 'T' && <Terminal mode={mode} url={url} />}\n"
     "        {tab === 'L' && <Lienzo snap={snap} />}\n"),
]


def parar(msg):
    print('\nNO SE TOCÓ NADA. ' + msg)
    sys.exit(1)


def leer(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


def escribir(p, txt):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write(txt)


def comprobar_raiz():
    for k in ('app', 'api', 'mock'):
        if not os.path.isfile(RUTAS[k]):
            parar(f'No encuentro {RUTAS[k]}. Ejecuta esto desde la raíz del repo (cd ~/neurotok).')


def aplicar():
    comprobar_raiz()
    cambios = {}   # ruta -> texto nuevo (se escribe todo al final, o nada)
    estado = []

    # App.js: reemplazos exactos
    t = leer(RUTAS['app'])
    for viejo, nuevo in APP_EDITS:
        if nuevo in t:
            continue
        if t.count(viejo) != 1:
            parar(f'App.js no coincide con lo esperado (busqué una sola vez):\n  {viejo.strip()[:90]}\n'
                  'Pásame el App.js actual y lo ajusto.')
        t = t.replace(viejo, nuevo)
    cambios[RUTAS['app']] = t

    # api.js y mock.js: se añade un bloque al final
    for clave, extra, marca, ancla in (('api', API_ADD, '// ---- Chat y Terminal (Tarea 2)', 'export const bovedaPost'),
                                       ('mock', MOCK_ADD, '// ---- Chat y Terminal simuladas (Tarea 2)', 'export const demoVault')):
        t = leer(RUTAS[clave])
        if marca not in t:
            if ancla not in t:
                parar(f'{RUTAS[clave]} no tiene "{ancla}": no es la versión esperada.')
            t = (t if t.endswith('\n') else t + '\n') + extra
        cambios[RUTAS[clave]] = t

    # Archivos nuevos (solo se sobrescriben si los creó esta misma tarea)
    for clave, contenido in (('chat', CHAT_JS), ('term', TERM_JS)):
        p = RUTAS[clave]
        if os.path.exists(p) and MARCA not in leer(p):
            parar(f'{p} ya existe y no es el de esta tarea. Renómbralo o bórralo y reintenta.')
        cambios[p] = contenido

    for p, txt in cambios.items():
        if not os.path.exists(p) or leer(p) != txt:
            escribir(p, txt)
            estado.append('escrito   ' + p)
        else:
            estado.append('sin cambio ' + p)
    print('\n'.join(estado))
    print('\nTarea 2 aplicada. Ahora: python fase_2.py probar')


def probar():
    comprobar_raiz()
    fallos = 0
    for k in ('chat', 'term'):
        if not os.path.isfile(RUTAS[k]):
            parar(f'Falta {RUTAS[k]}: primero corre  python fase_2.py')
    app = leer(RUTAS['app'])
    for pieza in ("import Chat from './src/Chat'", "import Terminal from './src/Terminal'", "['C', 'Chat']", "['T', 'Terminal']",
                  "['L', 'Lienzo']", "['B', 'Bóveda']", "['S', 'Ajustes']", "tab === 'L' && <Lienzo", "tab === 'B' && <Boveda", "tab === 'S' && <Ajustes"):
        if pieza not in app:
            print('  FALLA  App.js no contiene: ' + pieza)
            fallos += 1
    print('  ok  App.js: pestañas registradas y las anteriores siguen' if not fallos else '')

    npx = shutil.which('npx')
    if not npx:
        print('  AVISO  no hay npx: no pude comprobar la sintaxis JSX')
    else:
        for k in ('app', 'chat', 'term', 'api', 'mock'):
            r = subprocess.run([npx, '--yes', 'esbuild', RUTAS[k], '--loader:.js=jsx', '--log-level=error'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            if r.returncode == 0:
                print('  ok  sintaxis ' + RUTAS[k])
            else:
                print('  FALLA  sintaxis ' + RUTAS[k] + '\n' + r.stderr[:1500])
                fallos += 1

    node = shutil.which('node')
    if not node:
        print('  AVISO  no hay node: no corrí las pruebas de lógica')
    else:
        with tempfile.TemporaryDirectory() as d:
            shutil.copy(RUTAS['api'], os.path.join(d, 'api.mjs'))
            shutil.copy(RUTAS['mock'], os.path.join(d, 'mock.mjs'))
            escribir(os.path.join(d, 'prueba.mjs'), PRUEBA_MJS)
            r = subprocess.run([node, 'prueba.mjs'], cwd=d, capture_output=True, text=True)
            print(r.stdout.rstrip())
            if r.returncode != 0:
                print(r.stderr[-1500:])
                fallos += 1
    print('\nTODO OK' if not fallos else f'\n{fallos} FALLO(S): pásame esta salida completa.')
    sys.exit(1 if fallos else 0)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'probar':
        probar()
    else:
        aplicar()
