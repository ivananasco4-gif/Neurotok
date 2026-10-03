import React, { useEffect, useRef, useState } from 'react';
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
