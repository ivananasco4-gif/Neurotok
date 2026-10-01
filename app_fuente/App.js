import React, { useEffect, useRef, useState } from 'react';
import { Animated, Platform, SafeAreaView, ScrollView, StatusBar, StyleSheet, Text,
  TextInput, TouchableOpacity, View } from 'react-native';
import { demoInit, demoSnapshot, demoTick } from './src/mock';
import { auth, fetchAll, runGoal, stopRun } from './src/api';

const C = { bg: '#0b0f17', card: '#131a27', line: '#22304a', txt: '#e6edf7', mut: '#8b9bb4',
  ok: '#22c55e', warn: '#f59e0b', bad: '#ef4444', acc: '#6366f1', cyan: '#22d3ee' };
const MONO = Platform.OS === 'ios' ? 'Menlo' : 'monospace';
const fmt = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

// ---------------------------------------------------------------- datos (demo o API)
function useBrain(mode, url, token) {
  const [snap, setSnap] = useState(demoSnapshot(demoInit()));
  const [err, setErr] = useState('');
  const demo = useRef(demoInit());
  useEffect(() => {
    let alive = true;
    setErr('');
    const tick = async () => {
      if (mode === 'demo') {
        demo.current = demoTick(demo.current);
        setSnap(demoSnapshot(demo.current));
        return;
      }
      try { const d = await fetchAll(url); if (alive) { setSnap(d); setErr(''); } }
      catch (e) { if (alive) setErr(String(e.message || e)); }
    };
    tick();
    const id = setInterval(tick, mode === 'demo' ? 1000 : 2000);
    return () => { alive = false; clearInterval(id); };
  }, [mode, url, token]);
  return { snap, err };
}

// ---------------------------------------------------------------- piezas
const Card = ({ children, style }) => <View style={[s.card, style]}>{children}</View>;
const Title = ({ children }) => <Text style={s.h}>{children}</Text>;

function Badge({ n }) {
  const col = n.estado === 'DISPONIBLE' ? C.ok : n.estado === 'TRABAJANDO' ? C.warn : C.bad;
  const ico = n.estado === 'DISPONIBLE' ? '🟢' : n.estado === 'TRABAJANDO' ? '🟡' : '🔴';
  return (
    <View style={[s.badge, { borderColor: col }]}>
      <Text style={s.bId}>{ico} {n.id}</Text>
      <Text style={[s.bSt, { color: col }]}>
        {n.estado === 'EN_PAUSA' ? `COOLDOWN ${fmt(n.cooldown_restante_s)}` : n.estado}
      </Text>
    </View>
  );
}

function Node({ title, sub, color, children }) {
  return (
    <View style={[s.node, { borderColor: color }]}>
      <Text style={[s.nodeT, { color }]}>{title}</Text>
      {!!sub && <Text style={s.mut}>{sub}</Text>}
      <View style={{ marginTop: 8 }}>{children}</View>
    </View>
  );
}

function Pulse({ active, children }) {
  const a = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    if (!active) { a.setValue(1); return; }
    const loop = Animated.loop(Animated.sequence([
      Animated.timing(a, { toValue: 0.45, duration: 600, useNativeDriver: true }),
      Animated.timing(a, { toValue: 1, duration: 600, useNativeDriver: true })]));
    loop.start();
    return () => loop.stop();
  }, [active]);
  return <Animated.View style={{ opacity: a }}>{children}</Animated.View>;
}

// ---------------------------------------------------------------- Vista A
function VistaA({ snap }) {
  const ns = snap.neurons.neuronas;
  const by = (r) => ns.filter((n) => n.rol === r);
  const st = snap.status;
  return (
    <ScrollView contentContainerStyle={s.pad}>
      <Card>
        <Text style={s.mut}>OBJETIVO</Text>
        <Text style={s.txt}>{st.objetivo || '—'}</Text>
        <View style={s.barBg}><View style={[s.barFg, { width: `${st.progreso_pct}%` }]} /></View>
        <Text style={s.mut}>Paso {st.paso_actual} de {st.total_pasos} · {st.progreso_pct}% · {st.estado}</Text>
      </Card>

      <Node title="🧠 Cerebro Central" sub="Orquestador (Router)" color={C.cyan}>
        <View style={s.wrap}>{by('orquestador').map((n) => <Badge key={n.id} n={n} />)}</View>
      </Node>
      <View style={s.vline} />
      {[['arquitecto', '📐 Sub-Cerebro Arquitecto', 'Planificación y desglose', C.acc],
        ['creador', '⚙️ Sub-Cerebro Creador / Code', 'Qwen · DeepSeek · Groq', C.ok],
        ['auditor', '🛡️ Sub-Cerebro Auditor / Debugger', 'Claude · Grok', C.warn]].map(([r, t, sub, col]) => (
        <React.Fragment key={r}>
          <Node title={t} sub={sub} color={col}>
            <View style={s.wrap}>
              {by(r).length ? by(r).map((n) => <Badge key={n.id} n={n} />) : <Text style={s.mut}>Sin neuronas</Text>}
            </View>
          </Node>
          {r !== 'auditor' && <View style={s.vline} />}
        </React.Fragment>
      ))}
    </ScrollView>
  );
}

// ---------------------------------------------------------------- Vista B
function VistaB({ snap }) {
  const f = snap.flow;
  return (
    <ScrollView contentContainerStyle={s.pad}>
      <Card>
        <Title>Flujo en tiempo real</Title>
        {f.etapas.map((e, i) => (
          <View key={e.nombre}>
            <Pulse active={e.activa}>
              <View style={[s.stage, e.activa && { borderColor: C.cyan, backgroundColor: '#0e2230' }]}>
                <View style={[s.dot, { backgroundColor: e.activa ? C.cyan : C.line }]} />
                <Text style={[s.txt, !e.activa && { color: C.mut }]}>{e.nombre}</Text>
              </View>
            </Pulse>
            {i < f.etapas.length - 1 && <View style={s.vlineS} />}
          </View>
        ))}
        <Text style={[s.mut, { textAlign: 'center', marginTop: 8 }]}>↻ Feedback loop</Text>
      </Card>
      <Card>
        <Text style={s.mut}>COMANDO EN EJECUCIÓN</Text>
        <Text style={s.cmd}>$ {f.comando_activo || '—'}</Text>
      </Card>
      <Card>
        <Text style={s.mut}>AHORRO DE TOKENS (SANITIZADOR)</Text>
        <Text style={s.big}>{f.ahorro_pct}%</Text>
        <View style={s.barBg}><View style={[s.barFg, { width: `${Math.min(100, f.ahorro_pct)}%`, backgroundColor: C.ok }]} /></View>
      </Card>
    </ScrollView>
  );
}

// ---------------------------------------------------------------- Vista C
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
        if (l.startsWith('> ')) return <Text key={i} style={[s.mono, { color: C.bad }]}>{l.slice(2)}</Text>;
        if (l.startsWith('###')) return <Text key={i} style={[s.mono, { color: C.cyan }]}>{l.replace(/^#+\s*/, '')}</Text>;
        if (l.startsWith('**')) return <Text key={i} style={[s.mono, { color: C.warn }]}>{l.replace(/\*\*/g, '')}</Text>;
        return <Text key={i} style={[s.mono, inCode ? { color: '#c7f9cc' } : { color: C.txt }]}>{l.replace(/`/g, '')}</Text>;
      })}
    </View>
  );
}

function VistaC({ snap }) {
  const items = parseEstado(snap.boveda.estado_actual_md);
  const m = snap.boveda.metricas;
  return (
    <ScrollView contentContainerStyle={s.pad}>
      <Title>📚 00_estado_actual.md</Title>
      {items.map((it) => (
        <Card key={it.k}><Text style={s.mut}>{it.k.toUpperCase()}</Text><Text style={s.txt}>{it.v}</Text></Card>
      ))}
      <Card>
        <Text style={s.mut}>MÉTRICAS</Text>
        <Text style={s.txt}>Tokens crudos ≈ {m.tokens_crudos_aprox} → limpios ≈ {m.tokens_limpios_aprox}</Text>
        <Text style={[s.big, { fontSize: 22 }]}>Ahorro {m.ahorro_pct}%</Text>
      </Card>
      <Title>🖥️ Consola sanitizada</Title>
      <Consola md={snap.flow.consola_md} />
    </ScrollView>
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
        <Title>Modo</Title>
        <View style={s.row}>
          {['demo', 'api'].map((m) => (
            <TouchableOpacity key={m} onPress={() => setMode(m)}
              style={[s.pill, mode === m && { backgroundColor: C.acc, borderColor: C.acc }]}>
              <Text style={s.txt}>{m === 'demo' ? 'Demo (simulado)' : 'API real'}</Text>
            </TouchableOpacity>
          ))}
        </View>
        <Text style={[s.mut, { marginTop: 10 }]}>URL del servidor</Text>
        <TextInput style={s.input} value={url} onChangeText={setUrl} autoCapitalize="none"
          autoCorrect={false} placeholderTextColor={C.mut} />
        <Text style={[s.mut, { marginTop: 10 }]}>Token (en Termux: cat ~/.neurotok_token)</Text>
        <TextInput style={s.input} value={token} onChangeText={setToken} autoCapitalize="none"
          autoCorrect={false} secureTextEntry placeholderTextColor={C.mut} />
        {!!err && mode === 'api' && <Text style={{ color: C.bad, marginTop: 6 }}>{err}</Text>}
      </Card>
      <Card>
        <Title>Lanzar objetivo (modo API)</Title>
        <TextInput style={[s.input, { height: 80 }]} multiline value={goal} onChangeText={setGoal}
          placeholder="Ej: Crear un hola mundo en Python" placeholderTextColor={C.mut} />
        <View style={[s.row, { marginTop: 10 }]}>
          <TouchableOpacity style={[s.pill, { backgroundColor: C.ok, borderColor: C.ok }]}
            onPress={() => act(() => runGoal(url, goal))}><Text style={s.txt}>▶ Iniciar</Text></TouchableOpacity>
          <TouchableOpacity style={[s.pill, { backgroundColor: C.bad, borderColor: C.bad }]}
            onPress={() => act(() => stopRun(url))}><Text style={s.txt}>■ Detener</Text></TouchableOpacity>
        </View>
        {!!msg && <Text style={s.mut}>{msg}</Text>}
      </Card>
    </ScrollView>
  );
}

// ---------------------------------------------------------------- App
const TABS = [['A', '🧠 Cerebro'], ['B', '🔄 Flujo'], ['C', '📚 Bóveda'], ['S', '⚙️']];

export default function App() {
  const [tab, setTab] = useState('A');
  const [mode, setMode] = useState('demo');
  const [url, setUrl] = useState('http://127.0.0.1:8000');
  const [token, setToken] = useState('');
  auth.token = token;
  const { snap, err } = useBrain(mode, url, token);
  return (
    <SafeAreaView style={s.root}>
      <StatusBar barStyle="light-content" backgroundColor={C.bg} />
      <View style={s.top}>
        <Text style={s.title}>Neurotok</Text>
        <Text style={[s.tag, { color: mode === 'demo' ? C.warn : err ? C.bad : C.ok }]}>
          {mode === 'demo' ? '● DEMO' : err ? '● SIN CONEXIÓN' : '● EN VIVO'}
        </Text>
      </View>
      <View style={{ flex: 1 }}>
        {tab === 'A' && <VistaA snap={snap} />}
        {tab === 'B' && <VistaB snap={snap} />}
        {tab === 'C' && <VistaC snap={snap} />}
        {tab === 'S' && <Ajustes {...{ mode, setMode, url, setUrl, token, setToken, err }} />}
      </View>
      <View style={s.tabs}>
        {TABS.map(([k, label]) => (
          <TouchableOpacity key={k} style={s.tab} onPress={() => setTab(k)}>
            <Text style={[s.tabT, tab === k && { color: C.cyan }]}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg, paddingTop: Platform.OS === 'android' ? StatusBar.currentHeight : 0 },
  top: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 14 },
  title: { color: C.txt, fontSize: 18, fontWeight: '700' },
  tag: { fontSize: 12, fontWeight: '700' },
  pad: { padding: 12, paddingBottom: 30 },
  card: { backgroundColor: C.card, borderRadius: 12, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: C.line },
  h: { color: C.txt, fontSize: 16, fontWeight: '700', marginBottom: 8, marginTop: 4 },
  txt: { color: C.txt, fontSize: 14 },
  mut: { color: C.mut, fontSize: 12 },
  big: { color: C.ok, fontSize: 34, fontWeight: '800' },
  barBg: { height: 8, backgroundColor: C.line, borderRadius: 4, marginVertical: 8, overflow: 'hidden' },
  barFg: { height: 8, backgroundColor: C.acc, borderRadius: 4 },
  node: { backgroundColor: C.card, borderRadius: 14, borderWidth: 1.5, padding: 12 },
  nodeT: { fontSize: 15, fontWeight: '700' },
  vline: { width: 2, height: 18, backgroundColor: C.line, alignSelf: 'center' },
  vlineS: { width: 2, height: 10, backgroundColor: C.line, alignSelf: 'center' },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  badge: { borderWidth: 1, borderRadius: 10, paddingVertical: 6, paddingHorizontal: 10, backgroundColor: '#0f1522' },
  bId: { color: C.txt, fontSize: 13, fontWeight: '600' },
  bSt: { fontSize: 11, marginTop: 2, fontWeight: '700' },
  stage: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 10, borderRadius: 10, borderWidth: 1, borderColor: C.line },
  dot: { width: 10, height: 10, borderRadius: 5 },
  cmd: { color: '#c7f9cc', fontFamily: MONO, fontSize: 13, marginTop: 6 },
  term: { backgroundColor: '#05080d', borderRadius: 10, padding: 12, borderWidth: 1, borderColor: C.line },
  mono: { fontFamily: MONO, fontSize: 12, lineHeight: 17 },
  row: { flexDirection: 'row', gap: 10 },
  pill: { borderWidth: 1, borderColor: C.line, borderRadius: 20, paddingVertical: 8, paddingHorizontal: 16 },
  input: { backgroundColor: '#0f1522', color: C.txt, borderRadius: 8, borderWidth: 1, borderColor: C.line, padding: 10, marginTop: 6 },
  tabs: { flexDirection: 'row', borderTopWidth: 1, borderColor: C.line, backgroundColor: C.card },
  tab: { flex: 1, alignItems: 'center', paddingVertical: 14 },
  tabT: { color: C.mut, fontSize: 13, fontWeight: '600' },
});
