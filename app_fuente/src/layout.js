// Layouts estilo n8n (sin dependencias de React Native, para poder probarlos aparte)
export const CX = 300;
const DIR = { l: [-1, 0], r: [1, 0], t: [0, -1], b: [0, 1] };
const port = (n, s) => (s === 'l' ? [n.x, n.y + n.h / 2] : s === 'r' ? [n.x + n.w, n.y + n.h / 2]
  : s === 't' ? [n.x + n.w / 2, n.y] : [n.x + n.w / 2, n.y + n.h]);
const mmss = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
export const cut = (s, n) => { s = String(s ?? ''); return s.length > n ? s.slice(0, n - 1) + '…' : s; };

// Las aristas guardan solo los extremos; el camino se calcula con las posiciones actuales (nodos movibles)
export function edgePath(e, nodes) {
  const a = nodes[e.from], b = nodes[e.to];
  const [ax, ay] = port(a, e.sa);
  const [bx, by] = port(b, e.sb);
  const k = e.k ?? Math.max(30, Math.hypot(bx - ax, by - ay) / 2.2);
  return `M${ax} ${ay} C${ax + DIR[e.sa][0] * k} ${ay + DIR[e.sa][1] * k} ${bx + DIR[e.sb][0] * k} ${by + DIR[e.sb][1] * k} ${bx} ${by}`;
}

// Punto medio real de la curva (t = 0.5)
export function edgeMid(e, nodes) {
  const a = nodes[e.from], b = nodes[e.to];
  const [ax, ay] = port(a, e.sa);
  const [bx, by] = port(b, e.sb);
  const k = e.k ?? Math.max(30, Math.hypot(bx - ax, by - ay) / 2.2);
  const p1 = [ax + DIR[e.sa][0] * k, ay + DIR[e.sa][1] * k];
  const p2 = [bx + DIR[e.sb][0] * k, by + DIR[e.sb][1] * k];
  return [(ax + 3 * p1[0] + 3 * p2[0] + bx) / 8, (ay + 3 * p1[1] + 3 * p2[1] + by) / 8];
}

const sideToward = (cx, cy, px, py) => {
  const dx = px - cx, dy = py - cy;
  return Math.abs(dy) >= Math.abs(dx) ? (dy < 0 ? 't' : 'b') : (dx < 0 ? 'l' : 'r');
};

// Nodo chico "MD" (filtro Markdown) en medio de cada conector. Sigue al conector salvo que lo muevas a mano.
export const CHIP = { w: 34, h: 20 };
export function withChips(edges, nodes, pos) {
  const outNodes = {};
  const outEdges = [];
  edges.forEach((e) => {
    const id = `md:${e.id}`;
    const o = pos[id];
    const [cx, cy] = o ? [o.x + CHIP.w / 2, o.y + CHIP.h / 2] : edgeMid(e, nodes);
    outNodes[id] = { id, kind: 'md', x: cx - CHIP.w / 2, y: cy - CHIP.h / 2, w: CHIP.w, h: CHIP.h, t: 'MD', active: e.active };
    const [sx, sy] = port(nodes[e.from], e.sa);
    const [tx, ty] = port(nodes[e.to], e.sb);
    outEdges.push({ id: `${e.id}:a`, from: e.from, sa: e.sa, to: id, sb: sideToward(cx, cy, sx, sy), active: e.active });
    outEdges.push({ id: `${e.id}:b`, from: id, sa: sideToward(cx, cy, tx, ty), to: e.to, sb: e.sb, active: e.active });
  });
  return { nodes: outNodes, edges: outEdges };
}

export function boundsOf(nodes) {
  const a = Object.values(nodes).filter((n) => !n.hidden);
  if (!a.length) return { x0: 0, y0: 0, x1: 100, y1: 100 };
  return { x0: Math.min(...a.map((n) => n.x)) - 20, y0: Math.min(...a.map((n) => n.y)),
    x1: Math.max(...a.map((n) => n.x + n.w)), y1: Math.max(...a.map((n) => n.y + n.h)) };
}

// ---------------------------------------------------------------- Lienzo (cerebro)
export function buildGraph(neuronas, idx, running) {
  const nodes = {};
  const edges = [];
  const add = (id, cx, y, w, h, o) => { nodes[id] = { id, x: cx - w / 2, y, w, h, ...o }; return nodes[id]; };
  const link = (id, a, sa, b, sb, active, k) => edges.push({ id, from: a.id, sa, to: b.id, sb, active: !!active, k });
  const by = (r) => neuronas.filter((n) => n.rol === r);
  const working = (r) => by(r).some((n) => n.estado === 'TRABAJANDO');
  const neuronNode = (n, cx, y) => add(n.id, cx, y, 120, 40, {
    kind: 'neurona', estado: n.estado, t: n.id, full: n.id,
    s: n.estado === 'EN_PAUSA' ? `COOLDOWN ${mmss(n.cooldown_restante_s)}` : n.proveedor,
    glyph: n.estado === 'TRABAJANDO' ? 'run' : n.estado === 'EN_PAUSA' ? 'pause' : 'free',
    dashed: n.estado === 'EN_PAUSA', dim: n.estado === 'EN_PAUSA' });

  const humano = add('humano', CX, 0, 168, 52, { kind: 'main', t: 'Tú · Cerebelo', s: 'Idea / tarea', active: idx === 0 });
  const cerebro = add('cerebro', CX, 100, 168, 52, { kind: 'main', t: 'Gemini · Cerebro', s: 'Orquestador', active: !!running });
  link('humano-cerebro', humano, 'b', cerebro, 't', idx === 0);

  const orq = by('orquestador');
  orq.forEach((n, i) => {
    const nn = neuronNode(n, CX + 210, 106 + i * 46);
    link(`orq-${n.id}`, cerebro, 'r', nn, 'l', n.estado === 'TRABAJANDO');
  });

  const row2 = Math.max(230, 100 + orq.length * 46 + 70);
  const subs = [
    ['arquitecto', -200, 'Arquitecto', 'Planificación', 1],
    ['creador', 0, 'Creador / Code', 'Genera comandos', 2],
    ['auditor', 200, 'Auditor / Debug', 'Revisa errores', -1],
  ];
  let maxBottom = row2 + 48;
  let creadorOut = null;
  subs.forEach(([rol, dx, t, s, stage]) => {
    const active = idx === stage || working(rol);
    const sub = add(`sub_${rol}`, CX + dx, row2, 150, 48, { kind: 'main', t, s, active });
    link(`cerebro-${rol}`, cerebro, 'b', sub, 't', active);
    const list = by(rol);
    list.forEach((n, i) => {
      const nn = neuronNode(n, CX + dx + 90, row2 + 48 + 34 + i * 46);
      link(`${rol}-${n.id}`, sub, 'b', nn, 'l', n.estado === 'TRABAJANDO');
    });
    const bottom = list.length ? row2 + 48 + 34 + list.length * 46 - 6 : row2 + 48;
    maxBottom = Math.max(maxBottom, bottom);
    if (rol === 'creador') creadorOut = add('creador_out', CX + dx, bottom, 0, 0, { kind: 'pseudo', hidden: true });
  });

  const ty = maxBottom + 60;
  const termux = add('termux', CX, ty, 168, 52, { kind: 'main', t: 'Termux · Ejecutor', s: 'subprocess + timeout', active: idx === 3 });
  const sanit = add('sanit', CX, ty + 90, 168, 52, { kind: 'main', t: 'Sanitizador MD', s: 'filtro ANSI y tokens', active: idx === 4 });
  const lectora = add('lectora', CX, ty + 180, 168, 52, { kind: 'main', t: 'IA lectora', s: 'resume salidas largas', active: idx === 5 });
  const boveda = add('boveda', CX, ty + 270, 168, 52, { kind: 'main', t: 'Bóveda', s: '~/boveda_ia', active: idx === 5 });
  link('creador-termux', creadorOut, 'b', termux, 't', idx === 3);
  link('termux-sanit', termux, 'b', sanit, 't', idx === 4);
  link('sanit-lectora', sanit, 'b', lectora, 't', idx === 5);
  link('lectora-boveda', lectora, 'b', boveda, 't', idx === 5);
  link('boveda-cerebro', boveda, 'l', cerebro, 'l', idx === 5, 240);
  return { nodes, edges };
}

// ---------------------------------------------------------------- Bóveda: tareas → pasos → comandos
const GLYPH = { ok: 'ok', fallo: 'fail', en_curso: 'run' };

export function buildVaultGraph(tareas) {
  const nodes = {};
  const edges = [];
  const add = (id, x, y, w, h, o) => { nodes[id] = { id, x, y, w, h, ...o }; return nodes[id]; };
  const link = (id, a, b, active) => edges.push({ id, from: a.id, sa: 'r', to: b.id, sb: 'l', active: !!active });
  let y = 0;
  (tareas || []).forEach((t) => {
    const pasoNodes = [];
    (t.pasos || []).forEach((p) => {
      const cs = p.comandos || [];
      const cmdNodes = cs.map((c, i) => add(c.id, 420, y + i * 46, 200, 40, {
        kind: 'cmd', full: c.cmd, t: cut(c.cmd, 24), mono: true,
        s: c.estado === 'en_curso' ? 'ejecutando…' : `exit ${c.exit}`,
        glyph: GLYPH[c.estado] || 'free', dashed: c.estado === 'fallo', active: c.estado === 'en_curso' }));
      const blockH = Math.max(1, cs.length) * 46 - 6;
      const pn = add(p.id, 210, y + blockH / 2 - 24, 160, 48, {
        kind: 'paso', full: p.titulo, t: cut(p.titulo, 16), s: `${cs.length} comando${cs.length === 1 ? '' : 's'}`,
        glyph: GLYPH[p.estado] || 'free', dashed: p.estado === 'fallo', active: p.estado === 'en_curso' });
      cmdNodes.forEach((cn) => link(`${p.id}-${cn.id}`, pn, cn, cn.active));
      pasoNodes.push(pn);
      y += Math.max(1, cs.length) * 46 + 10;
    });
    const mid = pasoNodes.length
      ? (pasoNodes[0].y + pasoNodes[pasoNodes.length - 1].y) / 2 : y - 24;
    const tn = add(t.id, 0, mid, 170, 48, {
      kind: 'tarea', full: t.titulo, t: cut(t.titulo, 18), s: `${(t.pasos || []).length} pasos · ${t.estado}`,
      glyph: GLYPH[t.estado] || 'free', dashed: t.estado === 'fallo', active: t.estado === 'en_curso' });
    pasoNodes.forEach((pn) => link(`${t.id}-${pn.id}`, tn, pn, pn.active));
    y += 30;
  });
  return { nodes, edges };
}

// ---------------------------------------------------------------- Cuadrícula milimétrica
export function gridPaths({ x, y, k }, W, H) {
  const l = -x / k, t = -y / k, r = l + W / k, b = t + H / k;
  const showMinor = k >= 0.45;
  let minor = '', major = '';
  for (let gx = Math.floor(l / 10) * 10; gx <= r; gx += 10) {
    const isMajor = gx % 50 === 0;
    if (!isMajor && !showMinor) continue;
    const seg = `M${gx} ${t} L${gx} ${b} `;
    if (isMajor) major += seg; else minor += seg;
  }
  for (let gy = Math.floor(t / 10) * 10; gy <= b; gy += 10) {
    const isMajor = gy % 50 === 0;
    if (!isMajor && !showMinor) continue;
    const seg = `M${l} ${gy} L${r} ${gy} `;
    if (isMajor) major += seg; else minor += seg;
  }
  return { minor, major };
}
