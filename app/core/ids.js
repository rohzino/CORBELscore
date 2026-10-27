// Short random ids for boards, elements, buttons, tiles and conditions.
export function newId() {
  const c = globalThis.crypto;
  if (c?.randomUUID) return c.randomUUID().replace(/-/g, "").slice(0, 10);
  return Math.random().toString(16).slice(2, 12).padEnd(10, "0");
}
