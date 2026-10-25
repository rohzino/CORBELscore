// Live scoreboard data from Sportzcast (or any LiveXML/JSON feed).
//
//   mqtt     Recommended by Sportzcast. Cloud broker score.sportzcast.net:8883
//            (TLS; username = account e-mail, password = access token), or a
//            local ScoreConnect III / Scorelink+ broker on 1883 (no login).
//            Topic bot/{bot}/json, subscribe only.
//   tcp      Legacy socket on 1402: "GT <email> <token>" -> connection token;
//            "FB<bot>" -> serving node; then an XB/JB stream. STX/ETX framing.
//   livexml  The XML file written by Sportzcast LiveXML (or any XML/JSON file
//            or http URL), polled.   json: the same, for JSON.
// Payloads are flattened to {key: text} and fed to the engine; a field shows a
// live key when its source is set to it. Sources: docs.sportzcast.net.

import fs from "node:fs";
import net from "node:net";
import tls from "node:tls";
import { CLOUD_HOST, LEGACY_HOST, describeSource } from "../core/source.js";
import { newId } from "../core/ids.js";
import { parsePayload, splitFrames } from "./feeds.js";

export function mqttEncodeLength(n) {
  const out = [];
  do {
    let b = n % 128;
    n = Math.floor(n / 128);
    if (n) b |= 0x80;
    out.push(b);
  } while (n);
  return Buffer.from(out);
}

// [value, bytes used] or null when the buffer does not hold the whole length yet.
export function mqttDecodeLength(buf, pos) {
  let mult = 1, value = 0;
  for (let i = 0; i < 4; i++) {
    if (pos + i >= buf.length) return null;
    const b = buf[pos + i];
    value += (b & 0x7f) * mult;
    if (!(b & 0x80)) return [value, i + 1];
    mult *= 128;
  }
  throw new Error("Malformed MQTT length.");
}

const mqttStr = (s) => {
  const b = Buffer.from(s, "utf8");
  const h = Buffer.alloc(2);
  h.writeUInt16BE(b.length);
  return Buffer.concat([h, b]);
};

const CONNACK = { 1: "the broker does not accept MQTT 3.1.1", 2: "the client id was rejected", 3: "the broker is unavailable",
  4: "the e-mail or token is wrong", 5: "this account is not allowed to read that bot" };

class SourceError extends Error {}

function friendly(e) {
  if (e instanceof SourceError) return e.message;
  if (e.code === "ENOTFOUND" || e.code === "EAI_AGAIN") return "That address cannot be found. Check the host and the internet connection.";
  if (e.code === "ECONNREFUSED") return "The connection was refused. Is the device on, and the port right?";
  if (e.code === "ETIMEDOUT") return "The connection timed out.";
  if (e.code === "ECONNRESET") return "The connection was dropped.";
  return e.message || String(e);
}

export class SportzcastSource {
  // feed(values) and onStatus(status) are called as data and state change.
  constructor(settings, token, feed, onStatus = null) {
    this.s = settings;
    this.token = token || "";
    this.feed = feed;
    this.onStatus = onStatus;
    this.status = { state: "off", detail: "", packets: 0, last_packet: 0, keys: 0 };
    this.keys = {};
    this._gen = 0;          // bumps on every start/stop so stale callbacks do nothing
    this._sock = null;
    this._timers = new Set();
  }

  start() {
    this.stop();
    if (!this.s.kind) { this._set("off", ""); return; }
    const gen = ++this._gen;
    this._loop(gen, 1);
  }

  stop() {
    this._gen++;
    for (const t of this._timers) clearTimeout(t);
    this._timers.clear();
    if (this._sock) { try { this._sock.destroy(); } catch { /* */ } this._sock = null; }
    if (this.status.state !== "off") this._set("off", "");
  }

  // Called every second: live -> stale after stale_s of silence.
  checkStale() {
    const st = this.status;
    if (st.state === "live" && st.last_packet && Date.now() / 1000 - st.last_packet > this.s.stale_s) {
      this._set("stale", `Nothing received for ${Math.trunc(Date.now() / 1000 - st.last_packet)} s. Check the bot, its network, and that the scoreboard is on.`);
    }
  }

  _set(state, detail) {
    this.status = { ...this.status, state, detail };
    try { this.onStatus?.(this.status); } catch { /* */ }
  }

  _deliver(values) {
    if (!values || !Object.keys(values).length) return;
    Object.assign(this.keys, values);
    this.status.keys = Object.keys(this.keys).length;
    this.status.packets += 1;
    this.status.last_packet = Date.now() / 1000;
    this.feed(values);
    if (this.status.state !== "live") this._set("live", describeSource(this.s));
  }

  _wait(ms, gen) {
    return new Promise((resolve) => {
      const t = setTimeout(() => { this._timers.delete(t); resolve(gen === this._gen); }, ms);
      this._timers.add(t);
    });
  }

  async _loop(gen, backoff) {
    while (gen === this._gen) {
      try {
        if (this.s.kind === "mqtt") await this._runMqtt(gen);
        else if (this.s.kind === "tcp") await this._runTcp(gen);
        else if (this.s.kind === "livexml" || this.s.kind === "json") await this._runPoll(gen);
        else return;
        backoff = 1;
      } catch (e) {
        if (gen !== this._gen) return;
        this._set("error", `${friendly(e)} Retrying in ${backoff} s.`);
        if (!(await this._wait(backoff * 1000, gen))) return;
        backoff = Math.min(backoff * 2, 30);
      }
    }
  }

  _connect(host, port, useTls, gen) {
    return new Promise((resolve, reject) => {
      const opts = { host, port, timeout: 10_000 };
      const sock = useTls ? tls.connect({ ...opts, servername: host }) : net.connect(opts);
      const done = (err) => { sock.removeAllListeners("timeout"); if (err) { sock.destroy(); reject(err); } else resolve(sock); };
      sock.once(useTls ? "secureConnect" : "connect", () => { sock.removeAllListeners("error"); sock.setTimeout(0); done(); });
      sock.once("error", (e) => done(e));
      sock.once("timeout", () => done(Object.assign(new Error("The connection timed out."), { code: "ETIMEDOUT" })));
      if (gen !== this._gen) done(new SourceError("stopped"));
    });
  }

  // ----- MQTT ----------------------------------------------------------------------
  async _runMqtt(gen) {
    const s = this.s;
    const host = s.host || (s.cloud ? CLOUD_HOST : "");
    if (!host) throw new SourceError("Enter the local device's address.");
    const useTls = (s.cloud && !s.host) || s.port === 8883;
    const port = s.port || (useTls ? 8883 : 1883);
    if (s.cloud && !(s.username && this.token)) throw new SourceError("The Sportzcast cloud needs your account e-mail and access token.");
    this._set("connecting", `Connecting to ${host}:${port} …`);
    const sock = await this._connect(host, port, useTls, gen);
    if (gen !== this._gen) { sock.destroy(); return; }
    this._sock = sock;
    const keepalive = 30;
    const topic = `bot/${s.bot}/${s.data_type || "json"}`;
    await new Promise((resolve, reject) => {
      let buf = Buffer.alloc(0);
      let connected = false;
      let lastOut = Date.now();
      const send = (b) => { sock.write(b); lastOut = Date.now(); };
      const ping = setInterval(() => { if (Date.now() - lastOut > (keepalive / 2) * 1000) send(Buffer.from([0xc0, 0])); }, 1000);
      const finish = (err) => { clearInterval(ping); sock.removeAllListeners(); sock.destroy(); if (this._sock === sock) this._sock = null; err ? reject(err) : resolve(); };
      // CONNECT
      let flags = 0x02; // clean session
      let payload = mqttStr("corbelscore-" + newId());
      if (s.cloud && s.username) {
        flags |= 0x80;
        payload = Buffer.concat([payload, mqttStr(s.username)]);
        if (this.token) { flags |= 0x40; payload = Buffer.concat([payload, mqttStr(this.token)]); }
      }
      const ka = Buffer.alloc(2);
      ka.writeUInt16BE(keepalive);
      const body = Buffer.concat([mqttStr("MQTT"), Buffer.from([4, flags]), ka, payload]);
      send(Buffer.concat([Buffer.from([0x10]), mqttEncodeLength(body.length), body]));
      sock.on("data", (chunk) => {
        if (gen !== this._gen) return finish();
        buf = Buffer.concat([buf, chunk]);
        try {
          for (;;) {
            if (buf.length < 2) break;
            const len = mqttDecodeLength(buf, 1);
            if (!len) break;
            const [n, used] = len;
            const start = 1 + used;
            if (buf.length < start + n) break;
            const type = buf[0] >> 4, fl = buf[0] & 0x0f;
            const data = buf.subarray(start, start + n);
            buf = buf.subarray(start + n);
            if (type === 2) { // CONNACK
              if (data.length < 2) throw new SourceError("The broker did not answer the connection.");
              if (data[1] !== 0) throw new SourceError(`Connection refused: ${CONNACK[data[1]] ?? `code ${data[1]}`}.`);
              connected = true;
              const t = mqttStr(topic);
              const sb = Buffer.concat([Buffer.from([0, 1]), t, Buffer.from([0])]);
              send(Buffer.concat([Buffer.from([0x82]), mqttEncodeLength(sb.length), sb]));
              this._set("connecting", `Connected. Waiting for data on ${topic} …`);
            } else if (type === 9) { // SUBACK
              if (data[2] === 0x80) throw new SourceError("The broker refused the subscription. Check the bot number and your licence.");
            } else if (type === 3) { // PUBLISH
              const tlen = data.readUInt16BE(0);
              let pos = 2 + tlen;
              const qos = (fl >> 1) & 3;
              if (qos) {
                const pid = data.subarray(pos, pos + 2);
                pos += 2;
                if (qos === 1) send(Buffer.concat([Buffer.from([0x40, 2]), pid]));
              }
              try { this._deliver(parsePayload(data.subarray(pos))); } catch { /* one bad packet must not drop the link */ }
            }
          }
        } catch (e) { finish(e); }
      });
      sock.on("error", (e) => finish(e));
      sock.on("close", () => finish(connected ? new SourceError("The broker closed the connection.") : new SourceError("The broker did not answer the connection.")));
    });
  }

  // ----- legacy socket ---------------------------------------------------------------
  async _ask(host, port, command, gen) {
    const sock = await this._connect(host, port, false, gen);
    return new Promise((resolve) => {
      let buf = Buffer.alloc(0);
      const t = setTimeout(() => end(), 10_000);
      const end = () => {
        clearTimeout(t);
        sock.destroy();
        const [frames] = splitFrames(buf);
        resolve(frames.length ? frames[0] : Buffer.from(buf.toString("latin1").replace(/[\x02\x03]/g, ""), "latin1"));
      };
      sock.on("data", (c) => { buf = Buffer.concat([buf, c]); if (splitFrames(buf)[0].length) end(); });
      sock.on("end", end);
      sock.on("error", end);
      sock.write(command, "ascii");
    });
  }

  async _runTcp(gen) {
    const s = this.s;
    const port = s.port || 1402;
    const bot5 = String(Math.trunc(s.bot)).padStart(5, "0");
    const kind = ["xml", "xb"].includes((s.data_type || "").toLowerCase()) ? "XB" : "JB";
    let host, connToken;
    if (s.cloud) {
      if (!(s.username && this.token)) throw new SourceError("The Sportzcast socket needs your account e-mail and user token.");
      this._set("connecting", "Signing in …");
      const auth = (await this._ask(LEGACY_HOST, port, `GT ${s.username} ${this.token}`, gen)).toString("latin1").split("|");
      if (auth[0]?.trim() !== "1" || auth.length < 3) throw new SourceError("Sign-in refused. Check the e-mail and user token.");
      connToken = auth[2].trim();
      const node = (await this._ask(LEGACY_HOST, port, `FB${bot5}`, gen)).toString("latin1").trim();
      if (!node || node.toUpperCase().startsWith("ERR")) {
        await this._wait(10_000, gen); // Sportzcast asks for 10 s before retrying after ERR
        throw new SourceError(`Bot ${s.bot} is not being served right now.`);
      }
      host = s.host || node;
    } else {
      host = s.host;
      connToken = this.token;
      if (!host) throw new SourceError("Enter the local BotServer's address.");
    }
    if (gen !== this._gen) return;
    this._set("connecting", `Opening the ${kind === "XB" ? "XML" : "JSON"} stream for bot ${s.bot} …`);
    const sock = await this._connect(host, port, false, gen);
    this._sock = sock;
    await new Promise((resolve, reject) => {
      let buf = Buffer.alloc(0);
      const finish = (err) => { sock.removeAllListeners(); sock.destroy(); if (this._sock === sock) this._sock = null; err ? reject(err) : resolve(); };
      sock.on("data", (c) => {
        if (gen !== this._gen) return finish();
        buf = Buffer.concat([buf, c]);
        const [frames, rest] = splitFrames(buf);
        buf = rest.length > 1_000_000 ? Buffer.alloc(0) : rest;
        for (const f of frames) { try { this._deliver(parsePayload(f)); } catch { /* skip a bad frame */ } }
      });
      sock.on("error", (e) => finish(e));
      sock.on("close", () => finish(gen === this._gen ? new SourceError("The stream closed.") : null));
      sock.write(`${kind}${bot5}000000~${connToken}`, "ascii");
    });
  }

  // ----- file / URL polling -------------------------------------------------------------
  async _runPoll(gen) {
    const p = this.s.path.trim();
    if (!p) throw new SourceError("Choose the LiveXML file or URL.");
    const isUrl = /^https?:\/\//i.test(p);
    this._set("connecting", `Watching ${p} …`);
    let lastSig = null;
    while (gen === this._gen) {
      let data = null, sig;
      if (isUrl) {
        const ctl = new AbortController();
        const t = setTimeout(() => ctl.abort(), 5000);
        try {
          const r = await fetch(p, { signal: ctl.signal, cache: "no-store" });
          if (!r.ok) throw new SourceError(`${p} answered ${r.status}.`);
          data = Buffer.from(await r.arrayBuffer());
        } catch (e) {
          if (e.name === "AbortError") throw new SourceError(`${p} did not answer in time.`);
          throw e;
        } finally { clearTimeout(t); }
        sig = data.toString("base64");
      } else {
        let st;
        try { st = await fs.promises.stat(p); } catch (e) {
          if (e.code === "ENOENT") throw new SourceError(`${p} does not exist yet. Start LiveXML, or check the path.`);
          throw e;
        }
        sig = `${st.mtimeMs}:${st.size}`;
      }
      if (sig !== lastSig) {
        if (data === null) data = await fs.promises.readFile(p);
        let values = null;
        try { values = parsePayload(data); } catch { values = null; } // caught mid-write: keep the last good values
        if (values) { lastSig = sig; this._deliver(values); }
      }
      if (!(await this._wait(this.s.poll_ms, gen))) return;
    }
  }
}
