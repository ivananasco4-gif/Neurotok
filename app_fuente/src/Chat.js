// NEUROTOK-TAREA2: pestaña Chat con el cerebro. Archivo generado por fase_2.py.
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
