// Tiny SQL tokenizer for light highlighting and pretty line breaks. No dependency; not a parser.
export type SqlToken = { kind: "kw" | "str" | "num" | "cmt" | "txt"; text: string };

const BREAK_BEFORE = /^(SELECT|FROM|WHERE|GROUP\s+BY|ORDER\s+BY|HAVING|LIMIT|UNION(\s+ALL)?|(LEFT|RIGHT|INNER|FULL|CROSS)(\s+OUTER)?\s+JOIN|JOIN|WITH)$/i;
const KEYWORDS = "GROUP\\s+BY|ORDER\\s+BY|PARTITION\\s+BY|UNION(?:\\s+ALL)?|(?:LEFT|RIGHT|INNER|FULL|CROSS)(?:\\s+OUTER)?\\s+JOIN|"
  + "SELECT|FROM|WHERE|HAVING|LIMIT|JOIN|AND|OR|NOT|SUM|COUNT|AVG|MIN|MAX|DATE|AS|ON|BETWEEN|IN|IS|NULL|LIKE|DISTINCT|CASE|WHEN|THEN|ELSE|END|DESC|ASC|WITH|OVER|INTERVAL|CAST|NULLIF|COALESCE";
const TOKEN = new RegExp(`(--[^\\n]*|/\\*[\\s\\S]*?\\*/)|('(?:[^']|'')*'?)|(\\b\\d+(?:\\.\\d+)?\\b)|\\b(${KEYWORDS})\\b`, "gi");

export function tokenizeSql(sql: string): SqlToken[] {
  const out: SqlToken[] = [];
  let last = 0;
  const push = (kind: SqlToken["kind"], text: string) => { if (text) out.push({ kind, text }); };
  for (const m of sql.matchAll(TOKEN)) {
    push("txt", sql.slice(last, m.index));
    if (m[1]) push("cmt", m[0]); else if (m[2]) push("str", m[0]); else if (m[3]) push("num", m[0]); else push("kw", m[0]);
    last = (m.index ?? 0) + m[0].length;
  }
  push("txt", sql.slice(last));
  return out;
}

/** Highlight tokens; a single-line statement also gets a line break before each major clause. */
export function formatSql(sql: string): SqlToken[] {
  const src = sql.trim();
  const tokens = tokenizeSql(src);
  if (src.includes("\n")) return tokens;
  const out: SqlToken[] = [];
  let soFar = "";
  for (const t of tokens) {
    if (t.kind === "kw" && BREAK_BEFORE.test(t.text) && soFar.trim()) {
      soFar = soFar.replace(/[ \t]+$/, "");
      if (!soFar.endsWith("\n") && !soFar.endsWith("(")) { // keep "(SELECT ..." subqueries inline
        const prev = out[out.length - 1];
        if (prev?.kind === "txt") prev.text = prev.text.replace(/[ \t]+$/, "");
        out.push({ kind: "txt", text: "\n" }); soFar += "\n";
      }
    }
    out.push({ ...t }); soFar += t.text;
  }
  return out;
}
