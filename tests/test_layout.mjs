// Lienzo con cientos de neuronas OmniRoute: pocos nodos, sin NaN, ids estables. node tests/test_layout.mjs
import assert from 'node:assert/strict';
import { buildGraph, agruparNeuronas } from '../app_fuente/src/layout.js';

const EST = ['DISPONIBLE', 'TRABAJANDO', 'EN_PAUSA'];
const ROLES = ['creador', 'auditor', 'creador', 'arquitecto'];
const neuronas = (k) => {
  const out = [{ id: 'gemini_01', proveedor: 'gemini', rol: 'orquestador', estado: 'DISPONIBLE', cooldown_restante_s: 0, instancia: '' },
    { id: 'groq_01', proveedor: 'groq', rol: 'creador', estado: 'DISPONIBLE', cooldown_restante_s: 0, instancia: '' }];
  for (let i = 0; i < 5; i += 1) {
    for (let m = 0; m < 100; m += 1) {
      out.push({ id: `omni_0${i}/p${m % 7}/m${m}`, proveedor: 'omniroute', rol: ROLES[m % 4],
        estado: EST[(m + i + k) % 3], cooldown_restante_s: (m * 7 + k) % 300, instancia: `omni_0${i}` });
    }
  }
  return out;
};

const g1 = buildGraph(neuronas(0), 2, true, 'creador');
const ids1 = Object.keys(g1.nodes);
assert.ok(ids1.length <= 40, `demasiados nodos: ${ids1.length}`);
for (const n of Object.values(g1.nodes)) for (const v of [n.x, n.y, n.w, n.h]) assert.ok(Number.isFinite(v), n.id);
for (const e of g1.edges) assert.ok(g1.nodes[e.from] && g1.nodes[e.to], e.id);
assert.ok(g1.nodes['grupo:creador:omni_00'] && g1.nodes['grupo:arquitecto:omni_04']);
assert.ok(g1.nodes.sub_creador.active, 'el sub-cerebro activo debe marcarse');
const g2 = buildGraph(neuronas(1), 2, true, 'auditor');
assert.deepEqual(Object.keys(g2.nodes).sort(), ids1.sort(), 'los ids cambian al cambiar estados');

// sin solapes entre nodos visibles de la misma columna
const vis = Object.values(g1.nodes).filter((n) => !n.hidden);
for (const a of vis) for (const b of vis) {
  if (a === b) continue;
  const solapa = a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  assert.ok(!solapa, `solape ${a.id} / ${b.id}`);
}

// directas: hasta 6 sueltas, el resto agrupadas
const dir = Array.from({ length: 9 }, (_, i) => ({ id: `d${i}`, rol: 'creador', estado: 'DISPONIBLE', instancia: '' }));
const it = agruparNeuronas(dir);
assert.equal(it.filter((x) => x.tipo === 'neurona').length, 6);
assert.equal(it.find((x) => x.tipo === 'grupo').total, 3);
// un grupo con todo en pausa muestra la próxima liberación
const p = agruparNeuronas([{ id: 'o/a', instancia: 'o', estado: 'EN_PAUSA', cooldown_restante_s: 30 },
  { id: 'o/b', instancia: 'o', estado: 'EN_PAUSA', cooldown_restante_s: 12 }])[0];
assert.equal(p.proxima, 12); assert.equal(p.en_pausa, 2);
console.log(`OK: lienzo con ${neuronas(0).length} neuronas -> ${ids1.length} nodos`);
