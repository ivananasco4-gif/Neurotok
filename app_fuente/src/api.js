const j = async (base, path, opts) => {
  const r = await fetch(base + path, opts);
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
  j(base, '/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ objetivo }) });

export const stopRun = (base) => j(base, '/stop', { method: 'POST' });
