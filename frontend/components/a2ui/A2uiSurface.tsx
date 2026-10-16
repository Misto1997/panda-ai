"use client";
// Small A2UI v0.9 renderer: component tree by id, data-model bindings, PANDA catalog. Unknown or broken components render a
// safe fallback instead of crashing the page. (Chosen over @a2ui/react, see docs: that package is 0.x and pre-1.0.)
import React from "react";
import Chart from "../Chart";
import Markdown from "../Markdown";
import { BulletList, Callouts, Chips, DataTable, DecompositionTable, Heading, HypothesisList, KpiRow, SegmentBars, SqlBlock, SuggestionChips, VerdictHeader, type ChipItem, type DecompRow, type Hyp, type Kpi as KpiT, type SegCell, type Verdict } from "../blocks";
import type { Table } from "@/lib/types";
import { KNOWN_COMPONENTS, resolve, type Surface } from "./surface";

type Ctx = { surface: Surface };
type Props = Record<string, unknown>;
const MAX_DEPTH = 12;

const list = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);

// Each catalog entry: (resolved props, rendered children) -> node.
const registry: Record<string, (p: Props, children: React.ReactNode[]) => React.ReactNode> = {
  Column: (_p, children) => <div className="a2-col">{children}</div>,
  Text: (p) => <div className="answer"><Markdown text={String(p.text ?? "")} /></div>,
  KpiRow: (p) => { const items = list<KpiT>(p.items); return items.length ? <KpiRow items={items} /> : null; },
  VegaLiteChart: (p) => (p.spec && typeof p.spec === "object" ? <Chart spec={p.spec as Record<string, unknown>} /> : null),
  DataTable: (p) => (p.table ? <DataTable t={p.table as Table} /> : null),
  HypothesisList: (p) => <HypothesisList items={list<Hyp>(p.items)} />,
  DecompositionTable: (p) => <DecompositionTable rows={list<DecompRow>(p.rows)} title={p.title as string} format={p.format as string} />,
  SegmentBars: (p) => <SegmentBars cells={list<SegCell>(p.cells)} metric={p.metric as string} />,
  ChipRow: (p) => { const chips = list<ChipItem>(p.chips); return chips.length ? <Chips chips={chips} /> : null; },
  SqlBlock: (p) => (p.sql ? <SqlBlock sql={String(p.sql)} /> : null),
  SuggestionChips: (p) => <SuggestionChips items={list<string>(p.items).filter((x) => typeof x === "string")} />,
  VerdictHeader: (p) => (p.verdict && typeof p.verdict === "object" ? <VerdictHeader verdict={p.verdict as Verdict} /> : null),
  BulletList: (p) => <BulletList title={p.title as string | undefined} items={list<string>(p.items).filter((x) => typeof x === "string")} />,
  Callouts: (p) => <Callouts items={list<ChipItem>(p.items)} />,
  Heading: (p) => (p.text ? <Heading text={String(p.text)} /> : null),
  Grid: (_p, children) => <div className="a2-grid">{children}</div>,
};

class Boundary extends React.Component<{ label: string; children: React.ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <div className="muted">Could not display {this.props.label}.</div> : this.props.children; }
}

function Node({ id, ctx, depth }: { id: string; ctx: Ctx; depth: number }): React.ReactNode {
  const comp = ctx.surface.components[id];
  if (!comp || depth > MAX_DEPTH) return null; // missing reference: skip (progressive rendering)
  const render = KNOWN_COMPONENTS.has(comp.component) ? registry[comp.component] : undefined;
  if (!render) return <div className="muted">Unsupported component: {String(comp.component)}</div>;
  const props: Props = {};
  for (const [k, v] of Object.entries(comp)) props[k] = resolve(v, ctx.surface.data);
  const children = list<string>(comp.children).map((c) => <Node key={c} id={c} ctx={ctx} depth={depth + 1} />);
  return <Boundary label={comp.component}>{render(props, children)}</Boundary>;
}

export default function A2uiSurface({ surface }: { surface: Surface }) {
  return <div className={`result a2 ${surface.variant === "error" ? "error" : ""}`}><Node id="root" ctx={{ surface }} depth={0} /></div>;
}
