// NEUROTOK-TAREA2: pestaña Terminal (log en vivo + cola de aprobación). Archivo generado por fase_2.py.
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
