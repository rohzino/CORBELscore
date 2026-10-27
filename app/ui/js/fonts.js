// The fonts installed on this computer, for the designer's font list. Loaded
// when CORBELscore starts: the desktop app asks right away; in a browser the
// list arrives on the first click, because browsers only allow it after one.

let families = null;
let pending = null;
const listeners = new Set();

export const localFonts = () => families;
export const onLocalFonts = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };

export function loadLocalFonts() {
  if (families) return Promise.resolve(families);
  if (pending) return pending;
  if (!window.queryLocalFonts) return Promise.reject(new Error("This window cannot list the computer's fonts. Type the font's name instead."));
  pending = window.queryLocalFonts().then((list) => {
    families = [...new Set(list.map((f) => f.family))].sort((a, b) => a.localeCompare(b));
    for (const fn of listeners) { try { fn(families); } catch { /* */ } }
    return families;
  }).finally(() => { pending = null; });
  return pending;
}

// The desktop shell calls this as the window opens (it counts as a user action there).
window.__corbelLoadFonts = () => loadLocalFonts().then((f) => f.length).catch(() => 0);

// Elsewhere: try now, and once more on the first click if the browser wanted one.
loadLocalFonts().catch(() => {
  const once = () => { loadLocalFonts().catch(() => {}); };
  window.addEventListener("pointerdown", once, { once: true, capture: true });
});
