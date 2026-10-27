// A small, strict-enough XML reader for live-data feeds (LiveXML, Sportzcast
// XB streams). Elements, attributes, text, CDATA and the five entities plus
// numeric ones; comments, processing instructions and doctypes are skipped.
// Namespace prefixes are dropped. Returns { name, attrs, children, text }.

export class XmlError extends Error {}

const ENT = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" };
const decode = (s) => s.replace(/&(#x[0-9a-fA-F]+|#\d+|[a-zA-Z]+);/g, (m, e) => {
  if (e[0] === "#") {
    const n = e[1] === "x" || e[1] === "X" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
    try { return String.fromCodePoint(n); } catch { return m; }
  }
  return ENT[e] ?? m;
});
const local = (n) => (n.includes(":") ? n.slice(n.indexOf(":") + 1) : n);

export function parseXml(text) {
  let i = 0;
  const n = text.length;
  const stack = [];
  let root = null;
  const fail = (msg) => { throw new XmlError(`${msg} (at character ${i})`); };
  while (i < n) {
    if (text[i] !== "<") {
      const j = text.indexOf("<", i);
      const chunk = text.slice(i, j < 0 ? n : j);
      if (stack.length) stack.at(-1).text += decode(chunk);
      else if (chunk.trim()) fail("Text outside the root element");
      i = j < 0 ? n : j;
      continue;
    }
    if (text.startsWith("<!--", i)) { const j = text.indexOf("-->", i + 4); if (j < 0) fail("Unclosed comment"); i = j + 3; continue; }
    if (text.startsWith("<![CDATA[", i)) {
      const j = text.indexOf("]]>", i + 9);
      if (j < 0) fail("Unclosed CDATA");
      if (stack.length) stack.at(-1).text += text.slice(i + 9, j);
      i = j + 3;
      continue;
    }
    if (text.startsWith("<?", i)) { const j = text.indexOf("?>", i + 2); if (j < 0) fail("Unclosed declaration"); i = j + 2; continue; }
    if (text.startsWith("<!", i)) {
      // <!DOCTYPE ...> possibly with an internal subset [ ... ]
      let depth = 0, j = i + 2;
      for (; j < n; j++) { if (text[j] === "[") depth++; else if (text[j] === "]") depth--; else if (text[j] === ">" && depth <= 0) break; }
      i = j + 1;
      continue;
    }
    if (text[i + 1] === "/") {
      const j = text.indexOf(">", i);
      if (j < 0) fail("Unclosed end tag");
      const name = local(text.slice(i + 2, j).trim());
      const el = stack.pop();
      if (!el || el.name !== name) fail(`</${name}> does not match <${el?.name ?? "nothing"}>`);
      i = j + 1;
      continue;
    }
    // start tag
    const m = /^<([A-Za-z_][\w.:-]*)/.exec(text.slice(i, i + 256));
    if (!m) fail("Bad tag");
    const el = { name: local(m[1]), attrs: {}, children: [], text: "" };
    i += m[0].length;
    for (;;) {
      while (i < n && /\s/.test(text[i])) i++;
      if (text[i] === "/" && text[i + 1] === ">") { i += 2; attach(el, true); break; }
      if (text[i] === ">") { i += 1; attach(el, false); break; }
      const am = /^([A-Za-z_][\w.:-]*)\s*=\s*("([^"]*)"|'([^']*)')/.exec(text.slice(i, i + 65536));
      if (!am) fail(`Bad attribute in <${el.name}>`);
      // Namespace declarations are not data (as in Python's ElementTree).
      if (am[1] !== "xmlns" && !am[1].startsWith("xmlns:")) el.attrs[local(am[1])] = decode(am[3] ?? am[4] ?? "");
      i += am[0].length;
    }
  }
  if (stack.length) throw new XmlError(`<${stack.at(-1).name}> is not closed`);
  if (!root) throw new XmlError("No XML element found");
  return root;

  function attach(el, selfClosing) {
    if (stack.length) stack.at(-1).children.push(el);
    else if (root) fail("More than one root element");
    else root = el;
    if (!selfClosing) stack.push(el);
  }
}
