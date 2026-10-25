// Live data: parsers, a fake MQTT broker, a fake legacy socket, LiveXML files.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";

import { PRESETS } from "../app/core/presets.js";
import { makeSource } from "../app/core/source.js";
import { flattenJson, flattenXml, parsePayload, splitFrames, suggest } from "../app/service/feeds.js";
import { SportzcastSource, mqttDecodeLength, mqttEncodeLength } from "../app/service/sportzcast.js";
import { parseXml, XmlError } from "../app/service/xml.js";

const CONTRACT = { OriginTypeId: 2, OriginType: "Cloud", Clock: "4:07", FullClock: "4:07.0", ClockStatus: "R", EventId: 3, BotNumber: 175,
  GuestTeamName: "GUEST", HomeTeamName: "HOME", HomeScore: 42, GuestScore: 30, Period: 2 };
const LIVEXML = `<?xml version="1.0" encoding="utf-8"?>
<info><Hscore>42</Hscore><Vscore>30</Vscore><possession>H</possession>
<Htimeouts>4</Htimeouts><Vtimeouts>3</Vtimeouts><down>2</down><downtext>2nd</downtext></info>`;

const waitFor = async (cond, ms = 5000) => {
  const end = Date.now() + ms;
  while (Date.now() < end) { if (cond()) return true; await new Promise((r) => setTimeout(r, 20)); }
  return false;
};

test("parsers: flatten", () => {
  assert.deepEqual(flattenJson({ a: { b: 1 }, c: [5, null], d: true, e: 2.0 }), { "a.b": "1", "c.0": "5", "c.1": "", d: "1", e: "2" });
  let x = flattenXml(LIVEXML);
  assert.deepEqual([x.Hscore, x.downtext], ["42", "2nd"]);
  x = flattenXml('<r xmlns="urn:x"><t a="1"><v>1</v><v>2</v></t></r>');
  assert.deepEqual(x, { t_a: "1", "t.v.1": "1", "t.v.2": "2" });
  assert.equal(parsePayload(Buffer.from(JSON.stringify(CONTRACT))).HomeScore, "42");
  assert.equal(parsePayload(Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from(LIVEXML)])).Vscore, "30");
  assert.equal(parsePayload(Buffer.from("12|34|R")).field2, "34");
  assert.throws(() => parsePayload(Buffer.from("hello")));
});
test("parsers: xml details", () => {
  const r = parseXml(`<!DOCTYPE x [<!ENTITY a "b">]><!-- c --><x:root xmlns:x="u" k='v &amp; w'><a><![CDATA[1 < 2]]></a><b/>&#65;&#x42;</x:root>`);
  assert.equal(r.name, "root");
  assert.equal(r.attrs.k, "v & w");
  assert.equal(r.children[0].text, "1 < 2");
  assert.equal(r.text, "AB");
  for (const bad of ["<a><b></a>", "<a>", "<a></a><b></b>", "text", "<a x=1></a>"]) assert.throws(() => parseXml(bad), XmlError, bad);
});
test("parsers: framing", () => {
  const [frames, rest] = splitFrames(Buffer.from("junk\x02one\x03\x02two\x03\x02thr", "latin1"));
  assert.deepEqual(frames.map(String), ["one", "two"]);
  assert.equal(rest.toString("latin1"), "\x02thr");
});
test("parsers: mqtt lengths", () => {
  for (const n of [0, 127, 128, 16383, 16384, 2097151, 268435455]) {
    const enc = Buffer.concat([Buffer.from([0x30]), mqttEncodeLength(n)]);
    assert.deepEqual(mqttDecodeLength(enc, 1), [n, enc.length - 1]);
  }
  assert.equal(mqttDecodeLength(Buffer.from([0x30, 0x80]), 1), null);   // incomplete: wait for more
});
test("parsers: suggest", () => {
  const fields = [...PRESETS.Basketball().engine.fields.keys()];
  const m = suggest([...Object.keys(CONTRACT), "Hscore"], fields);
  assert.deepEqual([m["home.score"], m["away.score"], m["clock.game"], m.period, m["home.name"]], ["HomeScore", "GuestScore", "Clock", "Period", "HomeTeamName"]);
  const m2 = suggest(Object.keys(flattenXml(LIVEXML)), [...PRESETS.Football().engine.fields.keys()]);
  assert.deepEqual([m2["home.score"], m2["away.timeouts"], m2.down], ["Hscore", "Vtimeouts", "down"]);
});

// A one-client MQTT 3.1.1 broker that checks the login and publishes packets.
function fakeBroker({ user = "", password = "", payloads = [], qos = 0 } = {}) {
  const b = { topic: null, gotUser: null, pubacks: 0 };
  const str = (d, p) => { const n = d.readUInt16BE(p); return [d.subarray(p + 2, p + 2 + n).toString(), p + 2 + n]; };
  b.server = net.createServer((c) => {
    let buf = Buffer.alloc(0);
    const packets = [];
    let waiting = null;
    c.on("data", (chunk) => {
      buf = Buffer.concat([buf, chunk]);
      for (;;) {
        const len = buf.length >= 2 ? mqttDecodeLength(buf, 1) : null;
        if (!len || buf.length < 1 + len[1] + len[0]) break;
        packets.push([buf[0] >> 4, buf.subarray(1 + len[1], 1 + len[1] + len[0])]);
        buf = buf.subarray(1 + len[1] + len[0]);
      }
      if (waiting && packets.length) { const w = waiting; waiting = null; w(packets.shift()); }
    });
    c.on("error", () => {});
    const next = () => new Promise((r) => (packets.length ? r(packets.shift()) : (waiting = r)));
    (async () => {
      let [t, data] = await next();
      assert.equal(t, 1);
      let [name, pos] = str(data, 0);
      assert.equal(name, "MQTT");
      const flags = data[pos + 1];
      pos += 4;
      [, pos] = str(data, pos);
      let u = "", pw = "";
      if (flags & 0x80) [u, pos] = str(data, pos);
      if (flags & 0x40) [pw, pos] = str(data, pos);
      b.gotUser = u;
      const ok = u === user && pw === password;
      c.write(Buffer.from([0x20, 2, 0, ok ? 0 : 4]));
      if (!ok) { c.end(); return; }
      [t, data] = await next();
      assert.equal(t, 8);
      [b.topic] = str(data, 2);
      c.write(Buffer.concat([Buffer.from([0x90, 3]), data.subarray(0, 2), Buffer.from([0])]));
      for (let i = 0; i < payloads.length; i++) {
        const tp = Buffer.from(b.topic);
        const head = Buffer.alloc(2); head.writeUInt16BE(tp.length);
        let v = Buffer.concat([head, tp]);
        if (qos) { const id = Buffer.alloc(2); id.writeUInt16BE(i + 1); v = Buffer.concat([v, id]); }
        const body = Buffer.concat([v, payloads[i]]);
        c.write(Buffer.concat([Buffer.from([0x30 | (qos << 1)]), mqttEncodeLength(body.length), body]));
        if (qos) { const [pt] = await next(); if (pt === 4) b.pubacks++; }
        await new Promise((r) => setTimeout(r, 20));
      }
    })().catch(() => c.destroy());
  });
  return new Promise((resolve) => b.server.listen(0, "127.0.0.1", () => { b.port = b.server.address().port; resolve(b); }));
}

function runSource(t, settings, token = "") {
  const got = [], states = [];
  const src = new SportzcastSource(makeSource(settings), token, (v) => got.push(v), (st) => states.push([st.state, st.detail]));
  src.start();
  t.after(() => src.stop());
  return [src, got, states];
}

test("mqtt: local device", async (t) => {
  const b = await fakeBroker({ payloads: [Buffer.from(JSON.stringify(CONTRACT)), Buffer.from("not json"), Buffer.from(JSON.stringify({ HomeScore: 43 }))] });
  t.after(() => b.server.close());
  const [src, got, states] = runSource(t, { kind: "mqtt", cloud: false, host: "127.0.0.1", port: b.port, bot: 175 });
  assert.ok(await waitFor(() => got.length >= 2), JSON.stringify(states));
  assert.equal(b.topic, "bot/175/json");
  assert.equal(got[0].Clock, "4:07");
  assert.equal(got[1].HomeScore, "43");
  assert.equal(src.status.state, "live");
  assert.equal(src.keys.HomeScore, "43");
  assert.equal(b.gotUser, "");
});
test("mqtt: login and QoS 1", async (t) => {
  const b = await fakeBroker({ user: "me@example.com", password: "tok", payloads: [Buffer.from('{"HomeScore": 1}')], qos: 1 });
  t.after(() => b.server.close());
  const [, got, states] = runSource(t, { kind: "mqtt", cloud: true, host: "127.0.0.1", port: b.port, bot: 9, username: "me@example.com" }, "tok");
  assert.ok(await waitFor(() => got.length), JSON.stringify(states));
  assert.ok(await waitFor(() => b.pubacks === 1));
});
test("mqtt: wrong token", async (t) => {
  const b = await fakeBroker({ user: "me@example.com", password: "right" });
  t.after(() => b.server.close());
  const [src] = runSource(t, { kind: "mqtt", cloud: true, host: "127.0.0.1", port: b.port, bot: 9, username: "me@example.com" }, "wrong");
  assert.ok(await waitFor(() => src.status.state === "error"));
  assert.match(src.status.detail, /e-mail or token/);
});
test("mqtt: the cloud needs credentials", async (t) => {
  const [src] = runSource(t, { kind: "mqtt", cloud: true, bot: 1 });
  assert.ok(await waitFor(() => src.status.state === "error"));
  assert.match(src.status.detail, /e-mail and access token/);
});
test("legacy socket: local stream with a split frame", async (t) => {
  const request = [];
  const srv = net.createServer((c) => {
    c.once("data", async (d) => {
      request.push(d.toString());
      c.write(Buffer.from("\x02" + LIVEXML + "\x03\x02<info><Hscore>4", "utf8"));
      await new Promise((r) => setTimeout(r, 50));
      c.write("3</Hscore></info>\x03");
    });
    c.on("error", () => {});
  });
  await new Promise((r) => srv.listen(0, "127.0.0.1", r));
  t.after(() => srv.close());
  const [, got] = runSource(t, { kind: "tcp", cloud: false, host: "127.0.0.1", port: srv.address().port, bot: 5083, data_type: "xml" }, "TOK");
  assert.ok(await waitFor(() => got.length >= 2));
  assert.equal(request[0], "XB05083000000~TOK");
  assert.equal(got[0].Vscore, "30");
  assert.equal(got[1].Hscore, "43");
});
test("livexml: a file, including one caught mid-write", async (t) => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "ts-"));
  const file = path.join(d, "live.xml");
  fs.writeFileSync(file, LIVEXML);
  const [, got] = runSource(t, { kind: "livexml", path: file, poll_ms: 50 });
  assert.ok(await waitFor(() => got.length));
  fs.writeFileSync(file, "<info><Hscore>4");
  await new Promise((r) => setTimeout(r, 200));
  fs.writeFileSync(file, LIVEXML.replace(">42<", ">45<"));
  assert.ok(await waitFor(() => got.at(-1)?.Hscore === "45"));
  assert.ok(got.every((g) => "Hscore" in g));
});
test("livexml: a missing file, then silence turns amber", async (t) => {
  const [src] = runSource(t, { kind: "livexml", path: "/no/such/file.xml", poll_ms: 50 });
  assert.ok(await waitFor(() => src.status.state === "error"));
  assert.match(src.status.detail, /does not exist/);
  src.status.state = "live";
  src.status.last_packet = Date.now() / 1000 - 99;
  src.checkStale();
  assert.equal(src.status.state, "stale");
});
test("end to end: bot data into the engine", async (t) => {
  const p = PRESETS.Basketball();
  const e = p.engine;
  for (const [fk, sk] of Object.entries(suggest(Object.keys(CONTRACT), [...e.fields.keys()]))) e.field(fk).source = sk;
  e.field("period").rules = "1=1st|2=2nd|3=3rd|4=4th|5=OT";
  const b = await fakeBroker({ payloads: [Buffer.from(JSON.stringify(CONTRACT))] });
  t.after(() => b.server.close());
  const src = new SportzcastSource(makeSource({ kind: "mqtt", cloud: false, host: "127.0.0.1", port: b.port, bot: 1 }), "", (v) => e.feed(v));
  src.start();
  t.after(() => src.stop());
  assert.ok(await waitFor(() => { e.tick(); return e.snapshot().values["home.score"] === "42"; }));
  const v = e.snapshot().values;
  assert.deepEqual([v["away.score"], v["clock.game"], v.period, v["clock.game.running"]], ["30", "4:07", "2nd", "1"]);
});
