import React, { useEffect, useRef, useState } from 'react';
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
