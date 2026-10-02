import React, { memo, useEffect, useMemo, useRef, useState } from 'react';
import { PanResponder, Text, TouchableOpacity, View } from 'react-native';
import Svg, { Circle, G, Path, Rect, Text as SText } from 'react-native-svg';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { T } from './theme';
import { boundsOf, edgePath, gridPaths, withChips } from './layout';

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const DOTS = '1 7';

// Conectores inactivos: estáticos y memoizados (solo se redibujan si cambia su camino)
const Edge = memo(({ d }) => (
  <Path d={d} stroke={T.dot} strokeWidth={1.6} strokeLinecap="round" strokeDasharray={DOTS} fill="none" />
), (p, q) => p.d === q.d);

// Conectores activos: flujo violeta en vivo. La animación avanza por pasos (sin Animated) y se pausa mientras arrastras.
function ActiveEdges({ edges, paused }) {
  const [phase, setPhase] = useState(0);
  useEffect(() => {
    if (paused || !edges.length) return undefined;
    const id = setInterval(() => setPhase((p) => (p + 2) % 8), 80);
    return () => clearInterval(id);
  }, [paused, edges.length]);
  return (
    <G>
      {edges.map((e) => (
        <G key={e.id}>
          <Path d={e.d} stroke={T.violet} strokeOpacity={0.18} strokeWidth={7} fill="none" />
          <Path d={e.d} stroke={T.violet} strokeWidth={2.4} strokeLinecap="round"
            strokeDasharray={DOTS} strokeDashoffset={-phase} fill="none" />
        </G>
      ))}
    </G>
  );
}

// Estado por forma (sin colores): aro = libre, punto lleno = ok, aro punteado = pausa, X = falló, violeta = en vivo
function Glyph({ g, x, y }) {
  if (g === 'run') return <Circle cx={x} cy={y} r={4.5} fill={T.violet} stroke={T.violet} strokeWidth={1.4} />;
  if (g === 'ok') return <Circle cx={x} cy={y} r={4.5} fill={T.nodeTxt} stroke={T.nodeTxt} strokeWidth={1.4} />;
  if (g === 'fail') {
    return <Path d={`M${x - 4} ${y - 4} L${x + 4} ${y + 4} M${x + 4} ${y - 4} L${x - 4} ${y + 4}`}
      stroke={T.nodeTxt} strokeWidth={2} strokeLinecap="round" />;
  }
  return <Circle cx={x} cy={y} r={4.5} fill="none" stroke={T.nodeTxt} strokeWidth={1.4} strokeDasharray={g === 'pause' ? '2 2' : undefined} />;
}

function NodeImpl({ n }) {
  if (n.hidden) return null;
  if (n.kind === 'md') {
    return (
      <G>
        <Rect x={n.x} y={n.y} width={n.w} height={n.h} rx={6} fill={T.node}
          stroke={n.active ? T.violet : T.nodeBorder} strokeWidth={n.active ? 2 : 1} />
        <SText x={n.x + n.w / 2} y={n.y + n.h / 2 + 3.5} fontSize={10} fontWeight="bold" textAnchor="middle" fill={T.nodeTxt}>MD</SText>
      </G>
    );
  }
  const tx = n.glyph ? n.x + 28 : n.x + 14;
  const size = n.kind === 'neurona' ? 12 : n.kind === 'cmd' ? 11.5 : n.kind === 'main' ? 14 : 13;
  const cy = n.y + n.h / 2;
  const portDot = (cx, k) => <Circle key={k} cx={cx} cy={cy} r={3} fill={T.bg} stroke={T.nodeBorder} strokeWidth={1} />;
  return (
    <G opacity={n.dim ? 0.55 : 1}>
      <Rect x={n.x} y={n.y} width={n.w} height={n.h} rx={8} fill={T.node}
        stroke={n.active ? T.violet : T.nodeBorder} strokeWidth={n.active ? 2.5 : 1}
        strokeDasharray={n.dashed ? '4 3' : undefined} />
      {!!n.glyph && <Glyph g={n.glyph} x={n.x + 14} y={cy} />}
      <SText x={tx} y={cy - 3} fontSize={size} fontWeight="bold" fill={T.nodeTxt}
        fontFamily={n.mono ? 'monospace' : undefined}>{n.t}</SText>
      <SText x={tx} y={cy + 12} fontSize={10.5} fill={T.nodeSub}>{n.s}</SText>
      {portDot(n.x, 'l')}
      {portDot(n.x + n.w, 'r')}
    </G>
  );
}

const Node = memo(NodeImpl, (a, b) => {
  const p = a.n, q = b.n;
  return p.x === q.x && p.y === q.y && p.t === q.t && p.s === q.s && p.glyph === q.glyph
    && p.active === q.active && p.dim === q.dim && p.dashed === q.dashed;
});

export default function Canvas({ graph, storageKey, onNodePress, hud, emptyText, chips }) {
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [tf, setTf] = useState({ x: 0, y: 0, k: 0.6 });
  const [pos, setPos] = useState({});
  const [loaded, setLoaded] = useState(false);
  const st = useRef({ tf: { x: 0, y: 0, k: 0.6 }, size, pos: {}, nodes: {}, pd: 0, pm: null,
    mode: 'pan', id: null, start: null, moved: false, fitted: false, onPress: null, key: storageKey, raf: 0 });
  const [moving, setMoving] = useState(false);

  // posiciones guardadas de los nodos movidos
  useEffect(() => {
    let on = true;
    AsyncStorage.getItem(storageKey)
      .then((v) => { if (on && v) { const p = JSON.parse(v); st.current.pos = p; setPos(p); } })
      .catch(() => {})
      .finally(() => { if (on) setLoaded(true); });
    return () => { on = false; };
  }, [storageKey]);

  const base = useMemo(() => {
    const out = {};
    Object.values(graph.nodes).forEach((n) => { const o = pos[n.id]; out[n.id] = o ? { ...n, x: o.x, y: o.y } : n; });
    return out;
  }, [graph, pos]);
  const withMd = useMemo(() => (chips ? withChips(graph.edges, base, pos) : null), [chips, graph, base, pos]);
  const nodes = useMemo(() => (withMd ? { ...base, ...withMd.nodes } : base), [base, withMd]);
  const edgeDefs = withMd ? withMd.edges : graph.edges;
  const edges = useMemo(() => edgeDefs.map((e) => ({ ...e, d: edgePath(e, nodes) })), [edgeDefs, nodes]);
  const activos = useMemo(() => edges.filter((e) => e.active), [edges]);
  const inactivos = useMemo(() => edges.filter((e) => !e.active), [edges]);
  st.current.nodes = nodes;
  st.current.size = size;
  st.current.onPress = onNodePress;
  st.current.key = storageKey;

  const apply = (nt) => { st.current.tf = nt; setTf(nt); };
  const zoomAt = (cx, cy, f) => {
    const { x, y, k } = st.current.tf;
    const k2 = clamp(k * f, 0.25, 2.5);
    const f2 = k2 / k;
    apply({ k: k2, x: cx - (cx - x) * f2, y: cy - (cy - y) * f2 });
  };
  const fit = () => {
    const { w, h } = st.current.size;
    if (!w) return;
    const b = boundsOf(st.current.nodes);
    const bw = b.x1 - b.x0, bh = b.y1 - b.y0;
    const k = clamp(Math.min(w / (bw + 40), h / (bh + 40)), 0.25, 1.2);
    apply({ k, x: (w - bw * k) / 2 - b.x0 * k, y: (h - bh * k) / 2 - b.y0 * k });
  };
  const resetPos = () => {
    st.current.pos = {};
    setPos({});
    AsyncStorage.removeItem(st.current.key).catch(() => {});
    setTimeout(fit, 0);
  };

  useEffect(() => {
    if (size.w && loaded && !st.current.fitted && Object.keys(graph.nodes).length) { st.current.fitted = true; fit(); }
  }, [size, loaded, graph]);

  const hit = (lx, ly) => {
    const { x, y, k } = st.current.tf;
    const wx = (lx - x) / k, wy = (ly - y) / k, pad = 6;
    const arr = Object.values(st.current.nodes).filter((n) => !n.hidden);
    for (let i = arr.length - 1; i >= 0; i--) {
      const n = arr[i];
      if (wx >= n.x - pad && wx <= n.x + n.w + pad && wy >= n.y - pad && wy <= n.y + n.h + pad) return n;
    }
    return null;
  };

  const pan = useRef(PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: () => true,
    onPanResponderGrant: (e) => {
      const t = e.nativeEvent.touches;
      const s = st.current;
      s.pd = 0; s.pm = null; s.moved = false; s.id = null; s.mode = 'pan';
      setMoving(true);
      if (t.length === 1) {
        const n = hit(t[0].locationX, t[0].locationY);
        if (n) { s.mode = 'node'; s.id = n.id; s.start = { px: t[0].pageX, py: t[0].pageY, nx: n.x, ny: n.y }; }
      }
    },
    onPanResponderMove: (e) => {
      const t = e.nativeEvent.touches;
      const s = st.current;
      if (t.length >= 2) {
        s.mode = 'pan'; s.id = null; s.moved = true;
        const d = Math.hypot(t[0].pageX - t[1].pageX, t[0].pageY - t[1].pageY);
        if (s.pd) zoomAt((t[0].locationX + t[1].locationX) / 2, (t[0].locationY + t[1].locationY) / 2, d / s.pd);
        s.pd = d; s.pm = null;
      } else if (t.length === 1) {
        s.pd = 0;
        if (s.mode === 'node' && s.id) {
          const dx = t[0].pageX - s.start.px, dy = t[0].pageY - s.start.py;
          if (!s.moved && Math.hypot(dx, dy) < 6) return;
          s.moved = true;
          s.pos = { ...s.pos, [s.id]: { x: s.start.nx + dx / s.tf.k, y: s.start.ny + dy / s.tf.k } };
          if (!s.raf) s.raf = requestAnimationFrame(() => { s.raf = 0; setPos(st.current.pos); });
        } else {
          const p = { x: t[0].pageX, y: t[0].pageY };
          if (s.pm) { s.moved = true; apply({ ...s.tf, x: s.tf.x + p.x - s.pm.x, y: s.tf.y + p.y - s.pm.y }); }
          s.pm = p;
        }
      }
    },
    onPanResponderRelease: () => {
      const s = st.current;
      if (s.raf) { cancelAnimationFrame(s.raf); s.raf = 0; setPos(s.pos); }
      setMoving(false);
      if (s.mode === 'node' && s.id) {
        if (s.moved) AsyncStorage.setItem(s.key, JSON.stringify(s.pos)).catch(() => {});
        else if (s.onPress && s.nodes[s.id]) s.onPress(s.nodes[s.id]);
      }
      s.pd = 0; s.pm = null; s.id = null;
    },
    onPanResponderTerminate: () => { st.current.pd = 0; st.current.pm = null; st.current.id = null; setMoving(false); },
  })).current;

  const grid = useMemo(() => (size.w ? gridPaths(tf, size.w, size.h) : { minor: '', major: '' }), [tf, size]);
  const minor = moving ? '' : grid.minor;
  const btn = { width: 36, height: 36, borderRadius: 8, borderWidth: 1, borderColor: T.line, backgroundColor: T.panel,
    alignItems: 'center', justifyContent: 'center', marginBottom: 8 };

  return (
    <View style={{ flex: 1, backgroundColor: T.bg }}
      onLayout={(e) => setSize({ w: e.nativeEvent.layout.width, h: e.nativeEvent.layout.height })} {...pan.panHandlers}>
      {size.w > 0 && (
        <Svg width={size.w} height={size.h} pointerEvents="none">
          <G transform={`translate(${tf.x} ${tf.y}) scale(${tf.k})`}>
            <Path d={minor} stroke={T.gridMinor} strokeWidth={0.7 / tf.k} fill="none" />
            <Path d={grid.major} stroke={T.gridMajor} strokeWidth={1 / tf.k} fill="none" />
            {inactivos.map((e) => <Edge key={e.id} d={e.d} />)}
            <ActiveEdges edges={activos} paused={moving} />
            {Object.values(nodes).map((n) => <Node key={n.id} n={n} />)}
          </G>
        </Svg>
      )}
      {!Object.keys(graph.nodes).length && (
        <View pointerEvents="none" style={{ position: 'absolute', top: 40, left: 20, right: 20 }}>
          <Text style={{ color: T.mut, textAlign: 'center' }}>{emptyText || 'Sin nodos'}</Text>
        </View>
      )}
      <View style={{ position: 'absolute', top: 10, right: 10 }}>
        <TouchableOpacity style={btn} onPress={() => zoomAt(size.w / 2, size.h / 2, 1.25)}><Text style={{ color: T.txt, fontSize: 18 }}>+</Text></TouchableOpacity>
        <TouchableOpacity style={btn} onPress={() => zoomAt(size.w / 2, size.h / 2, 0.8)}><Text style={{ color: T.txt, fontSize: 18 }}>−</Text></TouchableOpacity>
        <TouchableOpacity style={btn} onPress={fit}><Text style={{ color: T.txt, fontSize: 16 }}>⌖</Text></TouchableOpacity>
        <TouchableOpacity style={btn} onPress={resetPos}><Text style={{ color: T.txt, fontSize: 16 }}>↺</Text></TouchableOpacity>
      </View>
      {!!hud && (
        <View pointerEvents="none" style={{ position: 'absolute', left: 10, right: 60, bottom: 10, backgroundColor: '#0b0b0dcc',
          borderWidth: 1, borderColor: T.line, borderRadius: 8, padding: 8 }}>
          <Text style={{ color: T.mut, fontSize: 10 }}>AHORRO DE TOKENS  <Text style={{ color: T.txt }}>{hud.ahorro}%</Text></Text>
          <Text numberOfLines={1} style={{ color: T.txt, fontSize: 12, marginTop: 3, fontFamily: 'monospace' }}>$ {hud.cmd || '—'}</Text>
        </View>
      )}
    </View>
  );
}
