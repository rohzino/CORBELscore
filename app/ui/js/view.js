// View tab: Graphics (design the on-air boards) and Live view (a clean,
// full-window picture of a board).

import { fileUrl, on, store } from "./api.js";
import { append, button, clear, h } from "./dom.js";
import { BoardView } from "/render/board-view.js";
import { attempt, remember, select, toast, ui } from "./ui.js";
import { mountDesigner } from "./designer.js";

export function mountView(root) {
  const view = h("div.view");
  const bar = h("div.subbar");
  const body = h("div", { style: { flex: "1", minHeight: "0", display: "flex", flexDirection: "column", position: "relative" } });
  view.append(bar, body);
  root.append(view);
  let inner = null;

  function renderBar() {
    clear(bar);
    bar.append(h("div.pagetabs", { role: "tablist" }, [["graphics", "Graphics"], ["live", "Live view"]].map(([id, label]) =>
      h("button", { role: "tab", "aria-selected": String(ui.viewSection === id), onclick: () => { ui.viewSection = id; remember(); show(); } }, label))));
    bar.append(h("span.spacer"));
    if (ui.viewSection === "live") liveTools(bar);
    else bar.append(h("span.hint", "Design the graphics that go on air. Text files and XML do not need a graphic."));
  }

  function show() {
    inner?.();
    clear(body);
    renderBar();
    inner = ui.viewSection === "live" ? mountLive(body) : mountDesigner(body);
  }

  // ---- live view ---------------------------------------------------------------------------
  let liveView = null;
  function liveTools(bar) {
    const p = store.project;
    if (!p.boards.some((b) => b.id === ui.liveBoard)) ui.liveBoard = p.boards[0]?.id;
    append(bar, [h("span.caps", "Board"), select(p.boards.map((b) => [b.id, b.name]), ui.liveBoard, (v) => { ui.liveBoard = v; remember(); show(); }, { k: "live-board" }),
      h("span.caps", "Behind"), select([["checker", "Checks (transparent)"], ["black", "Black"], ["green", "Green"]], ui.liveBg, (v) => { ui.liveBg = v; remember(); show(); }, { k: "live-bg" }),
      button("Full screen", () => body.requestFullscreen?.().catch(() => toast("Full screen is not available here.", true)), { title: "Esc leaves full screen" }),
      store.state.host.projector ? button("Projector window…", () => import("./api.js").then(({ call }) => attempt(() => call("/api/projector", { board: ui.liveBoard }))),
        { title: "Open this board in its own window, on any display" }) : null,
      button("Copy browser-source URL", () => {
        const w = store.status.web;
        if (!w?.running) return toast("Turn on the web server under Control → Edit → Outputs first.", true);
        const url = `${w.url.replace(/\/$/, "")}/board/${ui.liveBoard}`;
        navigator.clipboard.writeText(url).then(() => toast("Copied. In OBS add a Browser source with this address."), () => toast(url));
      })]);
  }

  function mountLive(el) {
    const p = store.project;
    const b = p.boards.find((x) => x.id === ui.liveBoard) ?? p.boards[0];
    const stage = h(`div.live-stage${ui.liveBg === "checker" ? ".checker" : ".bg-" + ui.liveBg}`);
    el.append(stage);
    liveView = new BoardView(stage, { assetUrl: fileUrl });
    liveView.setBoards(p.boards);
    liveView.setBoard(b, p.animations);
    if (store.snapshot) liveView.setValues(store.snapshot.values, store.snapshot.fx);
    const offs = [on("snap", (s) => liveView.setValues(s.values, s.fx)), on("project", (np) => { if (np) { const nb = np.boards.find((x) => x.id === ui.liveBoard); liveView.setBoards(np.boards); if (nb) liveView.setBoard(nb, np.animations); liveView.setValues(store.snapshot.values, store.snapshot.fx); } })];
    return () => { offs.forEach((f) => f()); liveView.destroy(); liveView = null; };
  }

  show();
  const off = on("project", (p) => { if (p && ui.viewSection === "live") renderBar(); });
  return () => { off(); inner?.(); };
}
