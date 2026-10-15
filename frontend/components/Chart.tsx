"use client";
import { useEffect, useRef } from "react";

export default function Chart({ spec }: { spec: Record<string, unknown> }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let view: { finalize: () => void } | undefined;
    import("vega-embed").then(({ default: embed }) => {
      if (!ref.current) return;
      embed(ref.current, spec as any, { actions: false, renderer: "svg", config: { font: "Inter, system-ui, sans-serif", axis: { labelColor: "#555", titleColor: "#555" } } })
        .then((r) => (view = r));
    });
    return () => view?.finalize();
  }, [spec]);
  return <div ref={ref} className="chart" />;
}
