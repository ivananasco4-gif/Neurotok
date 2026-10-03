// Datos simulados con la MISMA forma que devuelve api_server.py
const CMDS = ['pkg install -y python', 'pip install fastapi uvicorn', 'mkdir -p ~/proyectos_ia/app',
  'python -m py_compile main.py', 'python main.py', 'git init && git add .'];
const CONSOLAS = [
  '### Comando ejecutado\n`pip install fastapi uvicorn`\n**exit_code:** 0\n**stdout:**\n```text\nSuccessfully installed fastapi-0.115 uvicorn-0.32\n... [38 líneas omitidas por optimización de tokens] ...\n```',
  '### Comando ejecutado\n`python main.py`\n**exit_code:** 1\n**stdout:**\n```text\n(vacío)\n```\n**stderr:**\n> Traceback (most recent call last):\n>   File "main.py", line 3, in <module>\n> ModuleNotFoundError: No module named \'flask\'',
  '### Comando ejecutado\n`python -m py_compile main.py`\n**exit_code:** 0\n**stdout:**\n```text\n(vacío)\n```',
];
const ETAPAS = ['1. Idea Humana', '2. Sub-Cerebro Arquitecto', '3. Sub-Cerebro Creador',
  '4. Ejecutor Termux', '5. Sanitizador MD', '6. Bóveda Central'];
const SUB = { orquestador: 'Cerebro Central (Router)', arquitecto: 'Sub-Cerebro Arquitecto',
  creador: 'Sub-Cerebro Creador / Code', auditor: 'Sub-Cerebro Auditor / Debugger' };

const n = (id, proveedor, rol, estado, cd = 0) =>
  ({ id, proveedor, rol, estado, cooldown_restante_s: cd, sub_cerebro: SUB[rol], usos: 0, errores: 0 });

export const demoInit = () => ({
  t: 0, paso: 3, total: 7, raw: 18400, clean: 2100,
  neuronas: [
    n('gemini_01', 'gemini', 'orquestador', 'TRABAJANDO'),
    n('gemini_02', 'gemini', 'arquitecto', 'DISPONIBLE'),
    n('groq_01', 'groq', 'creador', 'TRABAJANDO'),
    n('deepseek_01', 'deepseek', 'creador', 'EN_PAUSA', 95),
    n('qwen_01', 'qwen', 'creador', 'DISPONIBLE'),
    n('claude_01', 'claude', 'auditor', 'DISPONIBLE'),
    n('grok_01', 'grok', 'auditor', 'EN_PAUSA', 40),
  ],
});

export function demoTick(s) {
  const t = s.t + 1;
  let neuronas = s.neuronas.map((x) => {
    if (x.estado !== 'EN_PAUSA') return x;
    const cd = x.cooldown_restante_s - 1;
    return cd <= 0 ? { ...x, estado: 'DISPONIBLE', cooldown_restante_s: 0 } : { ...x, cooldown_restante_s: cd };
  });
  if (t % 14 === 0) { // simula un 429
    const i = neuronas.findIndex((x) => x.rol === 'creador' && x.estado === 'TRABAJANDO');
    if (i >= 0) neuronas[i] = { ...neuronas[i], estado: 'EN_PAUSA', cooldown_restante_s: 60, errores: neuronas[i].errores + 1 };
    const j = neuronas.findIndex((x) => x.rol === 'creador' && x.estado === 'DISPONIBLE');
    if (j >= 0) neuronas[j] = { ...neuronas[j], estado: 'TRABAJANDO' };
  }
  const paso = s.paso + (t % 18 === 0 ? 1 : 0);
  return { ...s, t, neuronas, paso: paso > s.total ? 1 : paso,
    raw: s.raw + 350, clean: s.clean + 40 };
}

export function demoSnapshot(s) {
  const etapa = Math.floor(s.t / 3) % 6;
  const ahorro = Math.round((1 - s.clean / s.raw) * 1000) / 10;
  return {
    status: { objetivo: 'Crear API REST de ejemplo en Termux', estado: 'EJECUTANDO',
      progreso_pct: Math.round(((s.paso - 1) / s.total) * 100), paso_actual: s.paso,
      total_pasos: s.total, iteracion: s.t, neurona_activa: 'groq_01', error: '' },
    neurons: { neuronas: s.neuronas, sub_cerebros: SUB },
    flow: { etapas: ETAPAS.map((nombre, i) => ({ nombre, activa: i === etapa })),
      comando_activo: CMDS[Math.floor(s.t / 6) % CMDS.length], ahorro_pct: ahorro,
      consola_md: CONSOLAS[Math.floor(s.t / 9) % CONSOLAS.length] },
    boveda: {
      estado_actual_md: `# Estado actual\n**Objetivo General:** Crear API REST de ejemplo en Termux\n**Paso Actual:** ${s.paso} de ${s.total}\n**Última Acción y Resultado:** \`pip install fastapi\` -> exit 0\n**Tarea Pendiente Inmediata:** Crear main.py con endpoint /salud\n`,
      metricas: { tokens_crudos_aprox: Math.round(s.raw / 4), tokens_limpios_aprox: Math.round(s.clean / 4), ahorro_pct: ahorro },
    },
  };
}

// ---- Bóveda simulada: tareas → pasos → comandos, y reserva de comandos fallidos
export const demoVault = () => ({
  tareas: [
    { id: 't1', titulo: 'Crear API REST de ejemplo', estado: 'en_curso', pasos: [
      { id: 't1p1', titulo: 'Instalar dependencias', estado: 'ok', comandos: [
        { id: 't1p1c1', cmd: 'pkg install -y python', exit: 0, estado: 'ok' },
        { id: 't1p1c2', cmd: 'pip install fastapi', exit: 1, estado: 'fallo' },
        { id: 't1p1c3', cmd: 'pip install requests', exit: 0, estado: 'ok' } ] },
      { id: 't1p2', titulo: 'Crear main.py', estado: 'en_curso', comandos: [
        { id: 't1p2c1', cmd: "cat > main.py << 'EOF'", exit: 0, estado: 'ok' },
        { id: 't1p2c2', cmd: 'python main.py', exit: null, estado: 'en_curso' } ] } ] },
    { id: 't2', titulo: 'Inicializar repositorio git', estado: 'ok', pasos: [
      { id: 't2p1', titulo: 'git init y commit', estado: 'ok', comandos: [
        { id: 't2p1c1', cmd: 'git init -b main', exit: 0, estado: 'ok' },
        { id: 't2p1c2', cmd: 'git add . && git commit -m "init"', exit: 0, estado: 'ok' } ] } ] },
  ],
  fallidos: [
    { id: 'f1', cmd: 'pip install fastapi', error: 'pydantic-core necesita compilar Rust (no disponible en Termux)',
      tarea: 'Crear API REST de ejemplo', veces: 3, solucion: 'Usar http.server de la librería estándar', rehabilitado: false },
    { id: 'f2', cmd: 'apt install nodejs', error: 'apt no existe en este entorno: se usa pkg',
      tarea: 'Preparar entorno', veces: 1, solucion: 'pkg install nodejs-lts', rehabilitado: false },
    { id: 'f3', cmd: 'python main.py', error: "ModuleNotFoundError: No module named 'flask'",
      tarea: 'Crear API REST de ejemplo', veces: 2, solucion: '', rehabilitado: false },
  ],
});

// ---- Chat y Terminal simuladas (Tarea 2): misma forma que el contrato de la API
const D = { term: [], chat: [], pend: [], modo: 'manual', id: 1, seeded: false };
const hora = () => new Date().toTimeString().slice(0, 8);
const tl = (tipo, texto, crudo = null) => { D.term.push({ n: D.term.length, t: hora(), tipo, texto, crudo }); };
const cm = (rol, texto) => { D.chat.push({ n: D.chat.length, rol, texto, t: hora() }); };
const enqueue = (cmd, pensamiento, paso, riesgo = false) => { D.pend.push({ id: D.id++, cmd, pensamiento, paso, riesgo }); };

export function demoReset() {
  D.term = []; D.chat = []; D.pend = []; D.modo = 'manual'; D.id = 1; D.seeded = false;
}

function seed() {
  if (D.seeded) return;
  D.seeded = true;
  tl('info', 'Sesión de demostración: nada de esto se ejecuta de verdad.');
  cm('sistema', 'Modo Demo: todo es simulado.');
  cm('cerebro', 'Hola. Dime un objetivo y te propongo los comandos para cumplirlo.');
  cm('tu', 'Crea hola.py que imprima Neurotok y ejecútalo');
  cm('cerebro', 'Entendido. Son 3 pasos. Revisa la pestaña Terminal: ahí te pido aprobación para cada comando.');
  enqueue('pkg install -y python', 'Necesito Python instalado para poder ejecutar el script.', 1);
  enqueue("printf 'print(\"Neurotok\")\\n' > hola.py", 'Creo hola.py con una sola línea.', 2);
  enqueue('rm -rf ~/proyectos_ia/viejo', 'Limpio una carpeta antigua que estorba antes de seguir.', 3, true);
}

function ejecutar(cmd) {
  tl('cmd', cmd);
  if (/^pkg install/.test(cmd)) {
    tl('out', 'python ya está instalado (3.12.7)',
      'Reading package lists... Done\nBuilding dependency tree... Done\npython is already the newest version (3.12.7).\n0 upgraded, 0 newly installed, 0 to remove.');
  } else if (/^python3? hola\.py/.test(cmd)) {
    tl('out', 'Neurotok');
  } else if (/^echo /.test(cmd)) {
    tl('out', cmd.slice(5).replace(/^["']|["']$/g, ''));
  } else if (/^ls\b/.test(cmd)) {
    tl('out', 'hola.py', '-rw------- 1 u0_a217 u0_a217 22 Oct  3 17:20 hola.py\ntotal 4');
  } else if (/^(rm|printf|mkdir|cat)\b/.test(cmd)) {
    tl('out', '(sin salida)', '');
  } else {
    tl('err', 'demo: este comando no está simulado', `bash: ${cmd.split(' ')[0]}: simulado`);
  }
}

function cerrarCola() {
  if (!D.pend.length) cm('cerebro', 'Listo: la cola está vacía. Cuéntame el siguiente objetivo.');
}

export const demoApi = {
  terminal: async (desde = 0) => { seed(); return { siguiente: D.term.length, lineas: D.term.slice(desde) }; },
  pending: async () => {
    seed();
    if (D.modo === 'auto') { // en auto, lo que tiene riesgo sigue esperando a una persona
      const i = D.pend.findIndex((p) => !p.riesgo);
      if (i >= 0) {
        const [p] = D.pend.splice(i, 1);
        ejecutar(p.cmd);
        cm('sistema', `Auto: ejecutado ${p.cmd}`);
        cerrarCola();
      }
    }
    return { modo: D.modo, exec_habilitado: true, pendientes: D.pend.map((p) => ({ ...p })) };
  },
  approve: async (id, cmd) => {
    const i = D.pend.findIndex((p) => p.id === id);
    if (i < 0) throw new Error('Ese comando ya no está pendiente');
    const [p] = D.pend.splice(i, 1);
    const final = cmd !== undefined ? cmd : p.cmd;
    if (cmd !== undefined && cmd !== p.cmd) tl('info', 'Comando editado por ti antes de ejecutarlo');
    ejecutar(final);
    cm('sistema', `Ejecutado (paso ${p.paso}): ${final}`);
    cerrarCola();
    return { ok: true };
  },
  reject: async (id, motivo) => {
    const i = D.pend.findIndex((p) => p.id === id);
    if (i < 0) throw new Error('Ese comando ya no está pendiente');
    const [p] = D.pend.splice(i, 1);
    tl('info', `Rechazado: ${p.cmd}${motivo ? ` — ${motivo}` : ''}`);
    cm('sistema', `Rechazaste: ${p.cmd}${motivo ? ` (${motivo})` : ''}`);
    if (!D.pend.length) {
      cm('cerebro', 'Entendido, no lo ejecuto. Pruebo otro camino.');
      enqueue('ls -la ~/proyectos_ia', 'Antes de tocar nada, miro qué hay en la carpeta.', p.paso);
    }
    return { ok: true };
  },
  modo: async (modo) => {
    if (modo !== 'manual' && modo !== 'auto') throw new Error('modo inválido');
    D.modo = modo;
    tl('info', `Modo de aprobación: ${modo}`);
    return { ok: true };
  },
  exec: async (cmd) => { ejecutar(cmd); return { ok: true }; },
  chat: async (desde = 0) => { seed(); return { siguiente: D.chat.length, mensajes: D.chat.slice(desde) }; },
  chatPost: async (texto) => {
    seed();
    cm('tu', texto);
    cm('cerebro', `Objetivo recibido: "${texto}". Te propongo el primer comando en la Terminal.`);
    setTimeout(() => enqueue('ls -la ~/proyectos_ia', 'Empiezo viendo el estado de la carpeta de proyectos.', 1), 1200);
    return { ok: true };
  },
};
