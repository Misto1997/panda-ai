"use client";
import { useEffect, useRef, useState } from "react";

export default function Chart({ spec }: { spec: Record<string, unknown> }) {
  const ref = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let view: { finalize: () => void } | undefined;
    let cancelled = false;
    setFailed(false);
    import("vega-embed").then(({ default: embed }) => {
      if (!ref.current) return;
      return embed(ref.current, spec as any, { actions: false, renderer: "svg", config: { font: "Inter, system-ui, sans-serif", axis: { labelColor: "#555", titleColor: "#555" } } })
        .then((r) => { if (cancelled) r.finalize(); else view = r; });
    }).catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; view?.finalize(); };
  }, [spec]);
  if (failed) return <div className="muted">Chart unavailable</div>;
  return <div ref={ref} className="chart" />;
}
