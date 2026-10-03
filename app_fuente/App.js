import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Animated, Image, Modal, Platform, SafeAreaView, ScrollView, StatusBar, StyleSheet, Text, TextInput,
  TouchableOpacity, View } from 'react-native';
import { demoInit, demoSnapshot, demoTick, demoVault } from './src/mock';
import { auth, bovedaPost, fetchAll, getFallidos, getGrafo, runGoal, stopRun } from './src/api';
import Canvas from './src/Canvas';
import { buildGraph, buildVaultGraph } from './src/layout';
import { deleteNode, editNode } from './src/vaultOps';
import { T } from './src/theme';

const MONO = Platform.OS === 'ios' ? 'Menlo' : 'monospace';
const LOGO_RATIO = 1000 / 212;      // assets/logo.png
const WORDMARK_RATIO = 560 / 105;   // assets/wordmark_dark.png

// ---------------------------------------------------------------- Pantalla de entrada (logo)
function Intro({ onDone }) {
  const logoOp = useRef(new Animated.Value(0)).current;
  const fade = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    const anim = Animated.sequence([
      Animated.timing(logoOp, { toValue: 1, duration: 500, useNativeDriver: true }),
      Animated.delay(1100),
      Animated.timing(fade, { toValue: 0, duration: 450, useNativeDriver: true }),
    ]);
    anim.start(({ finished }) => { if (finished) onDone(); });
    return () => anim.stop();
  }, []);
  return (
    <Animated.View style={[StyleSheet.absoluteFill, s.intro, { opacity: fade }]}
      onStartShouldSetResponder={() => true} onResponderRelease={onDone}>
      <Animated.Image source={require('./assets/logo.png')} resizeMode="contain"
        style={{ width: '84%', aspectRatio: LOGO_RATIO, opacity: logoOp }} />
    </Animated.View>
  );
}

// ---------------------------------------------------------------- datos (demo o API)
function useBrain(mode, url, token) {
  const [snap, setSnap] = useState(demoSnapshot(demoInit()));
  const [err, setErr] = useState('');
  const demo = useRef(demoInit());
  useEffect(() => {
    let alive = true;
    let busy = false;
    setErr('');
    const tick = async () => {
      if (mode === 'demo') {
        demo.current = demoTick(demo.current);
        setSnap(demoSnapshot(demo.current));
        return;
      }
      if (busy) return;
      busy = true;
      try { const d = await fetchAll(url); if (alive) { setSnap(d); setErr(''); } }
      catch (e) { if (alive) setErr(String(e.message || e)); }
      finally { busy = false; }
    };
    tick();
    const id = setInterval(tick, mode === 'demo' ? 1000 : 500);
    return () => { alive = false; clearInterval(id); };
  }, [mode, url, token]);
  return { snap, err };
}

const Card = ({ children }) => <View style={s.card}>{children}</View>;
const Btn = ({ children, onPress, on }) => (
  <TouchableOpacity style={[s.pill, on && s.pillOn]} onPress={onPress}>
    <Text style={[s.txt, on && { color: T.nodeTxt }]}>{children}</Text>
  </TouchableOpacity>
);

// ---------------------------------------------------------------- Lienzo
function Lienzo({ snap }) {
  const st = snap.status;
  const running = st.estado === 'EJECUTANDO' || st.estado === 'PLANIFICANDO';
  const idx = snap.flow.etapas.findIndex((e) => e.activa);
  const graph = useMemo(() => buildGraph(snap.neurons.neuronas, idx, running), [snap.neurons, idx, running]);
  return (
    <View style={{ flex: 1 }}>
      <View style={s.strip}>
        <Text style={s.mut} numberOfLines={1}>{st.estado} · paso {st.paso_actual}/{st.total_pasos} · {st.progreso_pct}%</Text>
        <View style={s.barBg}><View style={[s.barFg, { width: `${st.progreso_pct}%` }]} /></View>
      </View>
      <Canvas graph={graph} chips storageKey="neurotok:pos:lienzo" hud={{ cmd: snap.flow.comando_activo, ahorro: snap.flow.ahorro_pct }} />
    </View>
  );
}

// ---------------------------------------------------------------- Bóveda
function parseEstado(md) {
  return (md || '').split('\n').map((l) => l.match(/^\*\*(.+?):\*\*\s*(.*)$/)).filter(Boolean)
    .map((m) => ({ k: m[1], v: m[2].replace(/`/g, '') }));
}

function Consola({ md }) {
  let inCode = false;
  return (
    <View style={s.term}>
      {(md || '').split('\n').map((l, i) => {
        if (l.startsWith('```')) { inCode = !inCode; return null; }
        if (l.startsWith('> ')) return <Text key={i} style={[s.mono, { color: '#fff', fontWeight: 'bold' }]}>▌{l.slice(2)}</Text>;
        if (l.startsWith('###')) return <Text key={i} style={[s.mono, { color: T.mut }]}>{l.replace(/^#+\s*/, '')}</Text>;
        if (l.startsWith('**')) return <Text key={i} style={[s.mono, { color: T.mut }]}>{l.replace(/\*\*/g, '')}</Text>;
        return <Text key={i} style={[s.mono, { color: inCode ? T.node : T.txt }]}>{l.replace(/`/g, '')}</Text>;
      })}
    </View>
  );
}

function Estado({ snap }) {
  const items = parseEstado(snap.boveda.estado_actual_md);
  const m = snap.boveda.metricas;
  return (
    <ScrollView contentContainerStyle={s.pad}>
      <Text style={s.h}>00_estado_actual.md</Text>
      {items.map((it) => (
        <Card key={it.k}><Text style={s.label}>{it.k.toUpperCase()}</Text><Text style={s.txt}>{it.v}</Text></Card>
      ))}
      <Card>
        <Text style={s.label}>MÉTRICAS</Text>
        <Text style={s.txt}>Tokens crudos ≈ {m.tokens_crudos_aprox} → limpios ≈ {m.tokens_limpios_aprox}</Text>
        <Text style={s.big}>{m.ahorro_pct}%</Text>
        <View style={s.barBg}><View style={[s.barFg, { width: `${Math.min(100, m.ahorro_pct)}%` }]} /></View>
        {m.consultas_boveda != null && (
          <Text style={[s.mut, { marginTop: 4 }]}>
            Consultas a la bóveda: {m.consultas_boveda} · fragmentos inyectados: {m.fragmentos_inyectados} · repetidos rechazados: {m.rechazos_repetidos} · fallidos activos: {m.fallidos_activos} · búsqueda {m.busqueda_fts5 ? 'FTS5' : 'básica'}
          </Text>
        )}
        {m.ahorro_busqueda_pct != null && <Text style={s.mut}>Ahorro por búsqueda (indicador, no tokens exactos): {m.ahorro_busqueda_pct}%</Text>}
      </Card>
      <Text style={s.h}>Consola sanitizada</Text>
      <Consola md={snap.flow.consola_md} />
    </ScrollView>
  );
}

function Fallidos({ list, onRehab, onDel }) {
  return (
    <ScrollView contentContainerStyle={s.pad}>
      <Text style={s.mut}>La IA recibe estos comandos como "no repetir". Rehabilita uno si el entorno cambió.</Text>
      {!list.length && <Text style={[s.txt, { marginTop: 14 }]}>No hay comandos fallidos.</Text>}
      {list.map((f) => (
        <View key={f.id} style={[s.card, { marginTop: 10 }, f.rehabilitado && { opacity: 0.55, borderStyle: 'dashed' }]}>
          <Text style={[s.txt, { fontFamily: MONO }]}>$ {f.cmd}</Text>
          <Text style={[s.mut, { marginTop: 6 }]}>{f.error}</Text>
          <Text style={[s.mut, { marginTop: 4 }]}>Falló {f.veces} {f.veces === 1 ? 'vez' : 'veces'} · {f.tarea}</Text>
          {!!f.solucion && <Text style={[s.txt, { marginTop: 6 }]}>↳ {f.solucion}</Text>}
          {f.rehabilitado && <Text style={[s.label, { marginTop: 6 }]}>REHABILITADO · SE PERMITE DE NUEVO</Text>}
          <View style={[s.row, { marginTop: 10 }]}>
            <Btn onPress={() => onRehab(f)}>{f.rehabilitado ? 'Volver a bloquear' : 'Rehabilitar'}</Btn>
            <Btn onPress={() => onDel(f)}>Borrar</Btn>
          </View>
        </View>
      ))}
    </ScrollView>
  );
}

const KIND = { tarea: 'tarea', paso: 'paso', cmd: 'comando' };

function Boveda({ snap, mode, url, vault, setVault }) {
  const live = mode === 'api';
  const [sec, setSec] = useState('estado');
  const [edit, setEdit] = useState(null);
  const [text, setText] = useState('');
  const [msg, setMsg] = useState('');
  const [api, setApi] = useState({ tareas: [], fallidos: [], err: '' });
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  const load = async () => {
    try {
      const [g, f] = await Promise.all([getGrafo(url), getFallidos(url)]);
      if (alive.current) setApi({ tareas: g.tareas || [], fallidos: Array.isArray(f) ? f : (f.fallidos || []), err: '' });
    } catch (e) { if (alive.current) setApi((a) => ({ ...a, err: String(e.message || e) })); }
  };
  useEffect(() => {
    if (!live || sec === 'estado') return undefined;
    load();
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, [live, sec, url]);

  const tareas = live ? api.tareas : vault.tareas;
  const fallidos = live ? api.fallidos : vault.fallidos;
  const graph = useMemo(() => buildVaultGraph(tareas), [tareas]);

  const open = (n) => { setEdit(n); setText(n.full || ''); setMsg(''); };
  const run = async (fn) => { try { await fn(); setEdit(null); if (live) load(); } catch (e) { setMsg(String(e.message || e)); } };
  const save = () => run(async () => {
    if (live) await bovedaPost(url, 'editar', { tipo: KIND[edit.kind], id: edit.rawId, [edit.kind === 'cmd' ? 'cmd' : 'titulo']: text });
    else setVault((v) => ({ ...v, tareas: editNode(v.tareas, edit.rawId, text) }));
  });
  const borrar = () => run(async () => {
    if (live) await bovedaPost(url, 'borrar', { tipo: KIND[edit.kind], id: edit.rawId });
    else setVault((v) => ({ ...v, tareas: deleteNode(v.tareas, edit.rawId) }));
  });
  const onRehab = (f) => {
    if (live) { bovedaPost(url, 'rehabilitar', { id: f.id, valor: !f.rehabilitado }).then(load).catch((e) => setApi((a) => ({ ...a, err: String(e.message || e) }))); return; }
    setVault((v) => ({ ...v, fallidos: v.fallidos.map((x) => (x.id === f.id ? { ...x, rehabilitado: !x.rehabilitado } : x)) }));
  };
  const onDel = (f) => {
    if (live) { bovedaPost(url, 'borrar', { tipo: 'fallido', id: f.id }).then(load).catch((e) => setApi((a) => ({ ...a, err: String(e.message || e) }))); return; }
    setVault((v) => ({ ...v, fallidos: v.fallidos.filter((x) => x.id !== f.id) }));
  };

  return (
    <View style={{ flex: 1 }}>
      <View style={s.seg}>
        {[['estado', 'Estado'], ['grafo', 'Grafo'], ['fallidos', 'Fallidos']].map(([k, label]) => (
          <TouchableOpacity key={k} style={[s.segItem, sec === k && s.segOn]} onPress={() => setSec(k)}>
            <Text style={[s.tabT, sec === k && { color: T.nodeTxt }]}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>
      {live && sec !== 'estado' && !!api.err && <Text style={[s.mut, { paddingHorizontal: 14, paddingBottom: 6 }]}>⚠ {api.err}</Text>}
      {sec === 'estado' && <Estado snap={snap} />}
      {sec === 'grafo' && (
        <Canvas key={live ? 'api' : 'demo'} graph={graph} storageKey={live ? 'neurotok:pos:boveda-api' : 'neurotok:pos:boveda'}
          onNodePress={open} emptyText="La bóveda aún no tiene tareas" />
      )}
      {sec === 'fallidos' && <Fallidos list={fallidos} onRehab={onRehab} onDel={onDel} />}
      <Modal visible={!!edit} transparent animationType="fade" onRequestClose={() => setEdit(null)}>
        <View style={s.modalBg}>
          <View style={s.modal}>
            <Text style={s.h}>Editar {edit ? KIND[edit.kind] : ''}</Text>
            <TextInput style={[s.input, { minHeight: 80, fontFamily: edit?.kind === 'cmd' ? MONO : undefined }]}
              multiline value={text} onChangeText={setText} autoCapitalize="none" autoCorrect={false} />
            {edit?.kind !== 'cmd' && <Text style={[s.mut, { marginTop: 6 }]}>Borrar también elimina lo que cuelga de este nodo.</Text>}
            {!!msg && <Text style={[s.txt, { marginTop: 6 }]}>⚠ {msg}</Text>}
            <View style={[s.row, { marginTop: 12 }]}>
              <Btn on onPress={save}>Guardar</Btn>
              <Btn onPress={borrar}>Borrar</Btn>
              <Btn onPress={() => setEdit(null)}>Cancelar</Btn>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

// ---------------------------------------------------------------- Ajustes
function Ajustes({ mode, setMode, url, setUrl, token, setToken, err }) {
  const [goal, setGoal] = useState('');
  const [msg, setMsg] = useState('');
  const act = async (fn) => { try { await fn(); setMsg('OK'); } catch (e) { setMsg(String(e.message || e)); } };
  return (
    <ScrollView contentContainerStyle={s.pad}>
      <Card>
        <Text style={s.h}>Modo</Text>
        <View style={s.row}>
          <Btn on={mode === 'demo'} onPress={() => setMode('demo')}>Demo</Btn>
          <Btn on={mode === 'api'} onPress={() => setMode('api')}>API real</Btn>
        </View>
        <Text style={[s.label, { marginTop: 12 }]}>URL DEL SERVIDOR</Text>
        <TextInput style={s.input} value={url} onChangeText={setUrl} autoCapitalize="none" autoCorrect={false} />
        <Text style={[s.label, { marginTop: 10 }]}>TOKEN (EN TERMUX: cat ~/.neurotok_token)</Text>
        <TextInput style={s.input} value={token} onChangeText={setToken} autoCapitalize="none" autoCorrect={false} secureTextEntry />
        {!!err && mode === 'api' && <Text style={[s.txt, { marginTop: 8 }]}>⚠ {err}</Text>}
      </Card>
      <Card>
        <Text style={s.h}>Lanzar objetivo (modo API)</Text>
        <TextInput style={[s.input, { height: 80 }]} multiline value={goal} onChangeText={setGoal}
          placeholder="Ej: Crear un hola mundo en Python" placeholderTextColor={T.mut} />
        <View style={[s.row, { marginTop: 10 }]}>
          <Btn on onPress={() => act(() => runGoal(url, goal))}>▶ Iniciar</Btn>
          <Btn onPress={() => act(() => stopRun(url))}>■ Detener</Btn>
        </View>
        {!!msg && <Text style={[s.mut, { marginTop: 8 }]}>{msg}</Text>}
      </Card>
    </ScrollView>
  );
}

// ---------------------------------------------------------------- App
const TABS = [['L', 'Lienzo'], ['B', 'Bóveda'], ['S', 'Ajustes']];

export default function App() {
  const [tab, setTab] = useState('L');
  const [mode, setMode] = useState('demo');
  const [url, setUrl] = useState('http://127.0.0.1:8000');
  const [token, setToken] = useState('');
  const [vault, setVault] = useState(demoVault());
  const [intro, setIntro] = useState(true);
  auth.token = token;
  const { snap, err } = useBrain(mode, url, token);
  const live = mode === 'api' && !err;
  return (
    <SafeAreaView style={s.root}>
      <StatusBar barStyle={intro ? 'dark-content' : 'light-content'} backgroundColor={intro ? '#ffffff' : T.bg} />
      <View style={s.top}>
        <Image source={require('./assets/wordmark_dark.png')} resizeMode="contain" style={{ height: 22, width: 22 * WORDMARK_RATIO }} />
        <Text style={[s.tag, live && { color: '#9b6dff' }]}>
          {mode === 'demo' ? '○ DEMO' : err ? '○ SIN CONEXIÓN' : '● EN VIVO'}
        </Text>
      </View>
      <View style={{ flex: 1 }}>
        {tab === 'L' && <Lienzo snap={snap} />}
        {tab === 'B' && <Boveda {...{ snap, mode, url, vault, setVault }} />}
        {tab === 'S' && <Ajustes {...{ mode, setMode, url, setUrl, token, setToken, err }} />}
      </View>
      <View style={s.tabs}>
        {TABS.map(([k, label]) => (
          <TouchableOpacity key={k} style={[s.tab, tab === k && s.tabOn]} onPress={() => setTab(k)}>
            <Text style={[s.tabT, tab === k && { color: T.txt }]}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>
      {intro && <Intro onDone={() => setIntro(false)} />}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: T.bg, paddingTop: Platform.OS === 'android' ? StatusBar.currentHeight : 0 },
  top: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12,
    borderBottomWidth: 1, borderColor: T.line },
  intro: { backgroundColor: '#ffffff', alignItems: 'center', justifyContent: 'center' },
  tag: { color: T.mut, fontSize: 11, fontWeight: '700', letterSpacing: 1 },
  strip: { paddingHorizontal: 16, paddingVertical: 8, borderBottomWidth: 1, borderColor: T.line },
  pad: { padding: 14, paddingBottom: 30 },
  card: { backgroundColor: T.panel, borderRadius: 10, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: T.line },
  h: { color: T.txt, fontSize: 14, fontWeight: '700', marginBottom: 8, marginTop: 4, letterSpacing: 0.5 },
  txt: { color: T.txt, fontSize: 14 },
  mut: { color: T.mut, fontSize: 12 },
  label: { color: T.mut, fontSize: 10, letterSpacing: 1, marginBottom: 4 },
  big: { color: T.txt, fontSize: 32, fontWeight: '800', marginTop: 6 },
  barBg: { height: 4, backgroundColor: T.line, borderRadius: 2, marginVertical: 6, overflow: 'hidden' },
  barFg: { height: 4, backgroundColor: T.node, borderRadius: 2 },
  term: { backgroundColor: '#060607', borderRadius: 8, padding: 12, borderWidth: 1, borderColor: T.line },
  mono: { fontFamily: MONO, fontSize: 12, lineHeight: 17 },
  row: { flexDirection: 'row', gap: 10, flexWrap: 'wrap' },
  pill: { borderWidth: 1, borderColor: T.line, borderRadius: 18, paddingVertical: 8, paddingHorizontal: 16 },
  pillOn: { backgroundColor: T.node, borderColor: T.node },
  input: { backgroundColor: T.bg, color: T.txt, borderRadius: 8, borderWidth: 1, borderColor: T.line, padding: 10, marginTop: 4 },
  seg: { flexDirection: 'row', margin: 12, borderWidth: 1, borderColor: T.line, borderRadius: 10, overflow: 'hidden' },
  segItem: { flex: 1, alignItems: 'center', paddingVertical: 9 },
  segOn: { backgroundColor: T.node },
  modalBg: { flex: 1, backgroundColor: '#000000cc', justifyContent: 'center', padding: 20 },
  modal: { backgroundColor: T.panel, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: T.line },
  tabs: { flexDirection: 'row', borderTopWidth: 1, borderColor: T.line, backgroundColor: T.bg },
  tab: { flex: 1, alignItems: 'center', paddingVertical: 14, borderTopWidth: 2, borderTopColor: 'transparent' },
  tabOn: { borderTopColor: T.node },
  tabT: { color: T.mut, fontSize: 12, fontWeight: '600', letterSpacing: 1 },
});
