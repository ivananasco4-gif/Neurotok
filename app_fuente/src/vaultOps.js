// Edición de la bóveda (modo Demo): cambiar texto o borrar tareas, pasos y comandos
export function editNode(tareas, id, text) {
  return tareas.map((t) => (t.id === id ? { ...t, titulo: text } : {
    ...t, pasos: t.pasos.map((p) => (p.id === id ? { ...p, titulo: text } : {
      ...p, comandos: p.comandos.map((c) => (c.id === id ? { ...c, cmd: text } : c)) })) }));
}

export function deleteNode(tareas, id) {
  return tareas.filter((t) => t.id !== id).map((t) => ({
    ...t, pasos: t.pasos.filter((p) => p.id !== id).map((p) => ({
      ...p, comandos: p.comandos.filter((c) => c.id !== id) })) }));
}
