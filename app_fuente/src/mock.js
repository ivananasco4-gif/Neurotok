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

// ---- Chat + Terminal demo
export const demoChatInit = () => ({
  mensajes: [
    { n: 1, rol: 'sistema', texto: 'Modo Demo activo. El backend no ejecuta comandos reales.', t: '16:00:00' },
    { n: 2, rol: 'cerebro', texto: 'Listo. Dime qué objetivo quieres conseguir.', t: '16:00:01' },
  ], next: 3, t: 0,
});
export const demoChatTick = (s) => s;
export const demoChatSend = (s, texto) => ({
  ...s,
  mensajes: [...s.mensajes,
    { n: s.next, rol: 'tu', texto, t: '16:00:02' },
    { n: s.next + 1, rol: 'cerebro', texto: 'Entendido. En modo Demo propondría los pasos y pediría aprobación antes de ejecutar.', t: '16:00:03' },
  ], next: s.next + 2,
});

export const demoTerminal = () => ({
  modo: 'manual', exec_habilitado: false, t: 0,
  lineas: [
    { n: 1, t: '16:00:01', tipo: 'info', texto: 'Demo iniciada: terminal simulada.', crudo: null },
    { n: 2, t: '16:00:02', tipo: 'cmd', texto: '$ pwd', crudo: '$ pwd' },
    { n: 3, t: '16:00:02', tipo: 'out', texto: '/data/data/com.termux/files/home/neurotok', crudo: '/data/data/com.termux/files/home/neurotok' },
  ],
  pendientes: [
    { id: 1, cmd: 'python -m py_compile backend/*.py', pensamiento: 'Validar sintaxis antes de continuar.', paso: 1, riesgo: false },
    { id: 2, cmd: 'rm -rf /tmp/demo', pensamiento: 'Ejemplo de comando marcado para revisión humana.', paso: 2, riesgo: true },
    { id: 3, cmd: 'git status --short', pensamiento: 'Comprobar cambios del repositorio.', paso: 3, riesgo: false },
  ],
});
export const demoPending = (s) => ({ ...s, t: s.t + 1 });
export const demoTerminalAction = (s, action, id, value) => {
  if (action === 'approve') return { ...s, pendientes: s.pendientes.filter((p) => p.id !== id), lineas: [...s.lineas, { n: s.lineas.length + 1, t: '16:00:04', tipo: 'cmd', texto: `$ ${value}`, crudo: `$ ${value}` }, { n: s.lineas.length + 2, t: '16:00:04', tipo: 'out', texto: 'exit 0 (Demo)', crudo: 'exit 0 (Demo)' }] };
  if (action === 'reject') return { ...s, pendientes: s.pendientes.filter((p) => p.id !== id), lineas: [...s.lineas, { n: s.lineas.length + 1, t: '16:00:05', tipo: 'info', texto: `Comando ${id} rechazado${value ? `: ${value}` : ''}.`, crudo: null }] };
  if (action === 'exec') return { ...s, lineas: [...s.lineas, { n: s.lineas.length + 1, t: '16:00:06', tipo: 'cmd', texto: `$ ${value}`, crudo: `$ ${value}` }] };
  return s;
};
