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

// ---- Chat + Terminal
export const getTerminal = (base, desde = 0) => j(base, `/terminal?desde=${encodeURIComponent(desde)}`);
export const getPending = (base) => j(base, '/pending');
export const approve = (base, id, cmd) => j(base, '/approve', { method: 'POST', body: JSON.stringify(cmd == null ? { id } : { id, cmd }) });
export const reject = (base, id, motivo) => j(base, '/reject', { method: 'POST', body: JSON.stringify(motivo ? { id, motivo } : { id }) });
export const setModo = (base, modo) => j(base, '/modo', { method: 'POST', body: JSON.stringify({ modo }) });
export const execManual = (base, cmd) => j(base, '/exec', { method: 'POST', body: JSON.stringify({ cmd }) });
export const getChat = (base, desde = 0) => j(base, `/chat?desde=${encodeURIComponent(desde)}`);
export const postChat = (base, texto) => j(base, '/chat', { method: 'POST', body: JSON.stringify({ texto }) });
