export const auth = { token: '' };

const headers = () => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${auth.token}` });

const j = async (base, path, opts = {}) => {
  const r = await fetch(base + path, { ...opts, headers: headers() });
  if (r.status === 401) throw new Error('Token incorrecto: revisa Ajustes');
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
};

export async function fetchAll(base) {
  const [status, neurons, flow, boveda] = await Promise.all([
    j(base, '/status'), j(base, '/neurons'), j(base, '/flow'), j(base, '/boveda'),
  ]);
  return { status, neurons, flow, boveda };
}

export const runGoal = (base, objetivo) =>
  j(base, '/run', { method: 'POST', body: JSON.stringify({ objetivo }) });

export const stopRun = (base) => j(base, '/stop', { method: 'POST' });

export const getGrafo = (base) => j(base, '/boveda/grafo');
export const getFallidos = (base) => j(base, '/boveda/fallidos');
export const bovedaPost = (base, ruta, body) => j(base, `/boveda/${ruta}`, { method: 'POST', body: JSON.stringify(body) });

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
