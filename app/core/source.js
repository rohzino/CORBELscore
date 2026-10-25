// Live-data connection settings (the connection itself runs in the service).
export const CLOUD_HOST = "score.sportzcast.net";
export const LEGACY_HOST = "scorebot.sportzcast.net";

export const SOURCE_DEFAULTS = {
  kind: "",          // "" (off) | mqtt | tcp | livexml | json
  cloud: true,       // mqtt/tcp: Sportzcast cloud; false = a device on this network
  host: "",          // local device address, or another broker/node
  port: 0,           // 0 = the standard port for the kind
  bot: 0,            // bot number
  username: "",      // account e-mail (the token is kept in this computer's settings, never the project)
  data_type: "json", // mqtt topic suffix / tcp stream: json or xml
  path: "",          // livexml/json: a file path or an http(s) URL
  poll_ms: 250,
  stale_s: 30,       // amber warning when nothing arrives for this long
};

export function makeSource(o = {}) {
  const s = { ...SOURCE_DEFAULTS };
  for (const k of Object.keys(SOURCE_DEFAULTS)) if (o?.[k] !== undefined) s[k] = o[k];
  s.kind = ["", "mqtt", "tcp", "livexml", "json"].includes(s.kind) ? s.kind : "";
  s.cloud = !!s.cloud;
  s.port = Math.trunc(Number(s.port) || 0);
  s.bot = Math.trunc(Number(s.bot) || 0);
  s.poll_ms = Math.max(50, Math.trunc(Number(s.poll_ms) || 250));
  s.stale_s = Math.max(1, Math.trunc(Number(s.stale_s) || 30));
  for (const k of ["host", "username", "data_type", "path"]) s[k] = String(s[k] ?? "");
  return s;
}

export function describeSource(s) {
  if (s.kind === "mqtt") return `Sportzcast MQTT · ${s.cloud ? CLOUD_HOST : s.host || "local device"} · bot ${s.bot}`;
  if (s.kind === "tcp") return `Sportzcast socket · bot ${s.bot}`;
  if (s.kind === "livexml" || s.kind === "json") return `${s.kind === "livexml" ? "LiveXML" : "JSON"} · ${s.path || "no file chosen"}`;
  return "Off";
}
