// Renders an SVG to a transparent PNG with Electron (no other tools needed):
//   Electron scripts/mac/render-svg.js in.svg out.png 1024
import { app, BrowserWindow } from "electron";
import fs from "node:fs";
const [svgFile, out, size = "1024"] = process.argv.slice(2);
const n = Number(size);
app.whenReady().then(async () => {
  try {
  const w = new BrowserWindow({ show: false, width: n, height: n, transparent: true, frame: false, useContentSize: true, webPreferences: { offscreen: true } });
  const svg = fs.readFileSync(svgFile, "utf8");
  await w.loadURL("data:text/html;charset=utf-8," + encodeURIComponent(`<style>html,body{margin:0;background:transparent}</style><img src="data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}" width=${n} height=${n}>`));
  await new Promise((r) => setTimeout(r, 400));
  fs.writeFileSync(out, (await w.webContents.capturePage()).toPNG());
  app.exit(0);
  } catch (err) { console.error(err); app.exit(1); }
});
