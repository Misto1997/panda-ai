// Minimal, XSS-safe inline renderer: **bold**, `code`, "- " bullets, paragraphs. No raw HTML is ever injected.
import React from "react";

function inline(s: string): React.ReactNode[] {
  return s.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((p, i) =>
    p.startsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> : p.startsWith("`") ? <code key={i}>{p.slice(1, -1)}</code> : <React.Fragment key={i}>{p}</React.Fragment>);
}

export default function Markdown({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/);
  return (
    <>
      {blocks.map((b, i) => {
        const lines = b.split("\n");
        const bullets = lines.filter((l) => l.startsWith("- "));
        if (bullets.length) {
          const lead = lines.filter((l) => !l.startsWith("- ")).join(" ");
          return (
            <div key={i}>
              {lead && <p>{inline(lead)}</p>}
              <ul>{bullets.map((l, j) => <li key={j}>{inline(l.slice(2))}</li>)}</ul>
            </div>
          );
        }
        return <p key={i}>{inline(b)}</p>;
      })}
    </>
  );
}
