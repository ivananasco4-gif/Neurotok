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
