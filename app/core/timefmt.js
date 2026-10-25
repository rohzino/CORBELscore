// Time formatting and parsing for TeleScore clocks.
//
// All clock values are integer milliseconds. Formatting is a pure function so the
// same rules apply to the operator panel, text files, XML and the browser source.
//
// Format tokens (case-insensitive):
//   h / hh   hours
//   m / mm   minutes (total minutes when the format has no hour token)
//   s / ss   seconds (total seconds when the format has no minute token)
//   t        tenths of a second   (`z` is accepted as the legacy spelling)
//   tt       hundredths of a second
// Anything else is copied literally, so `m:ss.t` renders `4:07.3`.

export const LEGACY_FORMATS = ["mm:ss", "hh:mm:ss", "m:ss", "mm", "ss", "hh", "mm:ss.z", "hh:mm:ss.z", "ss.z"];

const TOKEN = /(h+|m+|s+|t+|z+)/gi;

export class TimeParseError extends Error {}

const pad = (n, w) => String(n).padStart(w, "0");

// Quantise ms to unit. Whole-second countdowns round up, so 0.4 s left shows
// 0:01 and never 0:00 while the clock still runs. Tenths and hundredths
// truncate, as arena clocks do: the hand-off at one minute reads 1:00 -> 59.9.
function roundMs(ms, unit, countdown) {
  if (ms <= 0) return 0;
  if (countdown && unit >= 1000) return Math.ceil(ms / unit) * unit;
  return Math.floor(ms / unit) * unit;
}

export function formatMs(ms, fmt = "m:ss", countdown = true) {
  ms = Math.max(0, Math.trunc(Number(ms) || 0));
  const tokens = (fmt.match(TOKEN) || []).map((t) => t.toLowerCase());
  const hasH = tokens.some((t) => t[0] === "h");
  const hasM = tokens.some((t) => t[0] === "m");
  const hasS = tokens.some((t) => t[0] === "s");
  const frac = tokens.filter((t) => t[0] === "t" || t[0] === "z");
  let unit;
  if (frac.some((t) => t.length >= 2)) unit = 10;
  else if (frac.length) unit = 100;
  else if (hasS) unit = 1000;
  else if (hasM) unit = 60_000;
  else if (hasH) unit = 3_600_000;
  else unit = 1000;
  const q = roundMs(ms, unit, countdown);
  const hours = Math.floor(q / 3_600_000);
  const minutes = hasH ? Math.floor(q / 60_000) % 60 : Math.floor(q / 60_000);
  const seconds = hasH || hasM ? Math.floor(q / 1000) % 60 : Math.floor(q / 1000);
  const tenths = Math.floor(q / 100) % 10;
  const hundredths = Math.floor(q / 10) % 100;
  return fmt.replace(TOKEN, (tok) => {
    const kind = tok[0].toLowerCase();
    const width = tok.length;
    if (kind === "h") return pad(hours, width);
    if (kind === "m") return pad(minutes, width);
    if (kind === "s") return pad(seconds, width);
    return width >= 2 ? pad(hundredths, 2) : String(tenths);
  });
}

const PARSE = /^\s*(?:(\d+)\s*:\s*)?(?:(\d+)\s*:\s*)?(\d+)?(?:[.,](\d{1,3}))?\s*$/;

// Operator input -> milliseconds. Accepts 12:00, 1:02:03, 45 (seconds),
// 4:07.3, .5, 8: (minutes), 90 (90 seconds).
export function parseTime(text) {
  let raw = String(text ?? "").trim();
  if (!raw) throw new TimeParseError("Type a time such as 12:00 or 45.");
  if (raw.endsWith(":")) raw += "00";
  const m = PARSE.exec(raw);
  if (!m || (m[3] === undefined && m[4] === undefined && m[1] === undefined)) {
    throw new TimeParseError(`"${text}" is not a time. Use m:ss, h:mm:ss or seconds.`);
  }
  const parts = [m[1], m[2], m[3]].filter((p) => p !== undefined).map(Number);
  let h = 0, mi = 0, s = 0;
  if (parts.length === 3) [h, mi, s] = parts;
  else if (parts.length === 2) [mi, s] = parts;
  else if (parts.length === 1) [s] = parts;
  if (parts.length >= 2 && s >= 60) throw new TimeParseError(`"${text}": seconds must be under 60 when minutes are given.`);
  if (parts.length === 3 && mi >= 60) throw new TimeParseError(`"${text}": minutes must be under 60 when hours are given.`);
  const f = m[4] || "";
  const fracMs = f ? Number((f + "00").slice(0, 3)) : 0;
  return ((h * 60 + mi) * 60 + s) * 1000 + fracMs;
}

// 1 -> 1st, 2 -> 2nd, 11 -> 11th, 112 -> 112th, 21 -> 21st.
export function ordinal(n) {
  n = Math.trunc(Number(n));
  const a = Math.abs(n);
  const suffix = a % 100 >= 10 && a % 100 <= 20 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" }[a % 10] || "th");
  return `${n}${suffix}`;
}
