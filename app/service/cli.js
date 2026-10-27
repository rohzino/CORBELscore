// Run CORBELscore's service without the Electron window (tests, a server box,
// or a browser on another machine with --lan). Prints the studio address.
//   node app/service/cli.js [--port 5170] [--data <dir>] [--preset Basketball] [--open file.corbel]

import os from "node:os";
import path from "node:path";
import { App } from "./app.js";

const args = process.argv.slice(2);
const opt = (name, dflt) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : dflt; };
const dataDir = opt("--data", path.join(os.homedir(), ".corbelscore"));
const app = new App({ dataDir, studioPort: Number(opt("--port", 0)) });
const url = await app.start();
if (opt("--open")) await app.openFile(opt("--open"));
else if (opt("--preset")) await app.newProject(opt("--preset"));
console.log(`CORBELscore studio: ${url}`);
const quit = async () => { await app.stop(); process.exit(0); };
process.on("SIGINT", quit);
process.on("SIGTERM", quit);
