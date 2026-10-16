// A2UI v0.9 surface state: apply createSurface / updateComponents / updateDataModel / deleteSurface messages.
import type { A2uiComponent, A2uiMessage } from "@/lib/types";
import catalog from "./catalog.json";

export const CATALOG_ID: string = catalog.catalogId;
export const KNOWN_COMPONENTS = new Set(Object.keys(catalog.components));

export type Surface = { surfaceId: string; catalogId: string; variant?: string; components: Record<string, A2uiComponent>; data: unknown };
export type Surfaces = Record<string, Surface>;

const tokens = (path: string) => path.split("/").slice(1).map((t) => t.replaceAll("~1", "/").replaceAll("~0", "~"));

export function getPointer(data: unknown, path: string): unknown {
  let cur: any = data;
  for (const t of path === "/" || path === "" ? [] : tokens(path)) {
    if (cur === null || typeof cur !== "object") return undefined;
    cur = cur[t];
  }
  return cur;
}

function setPointer(data: any, path: string | undefined, value: unknown): unknown {
  if (!path || path === "/") return value;
  const ts = tokens(path), root = Array.isArray(data) ? [...data] : { ...(data ?? {}) };
  let cur: any = root;
  ts.forEach((t, i) => {
    if (i === ts.length - 1) { if (value === undefined) delete cur[t]; else cur[t] = value; return; }
    cur[t] = Array.isArray(cur[t]) ? [...cur[t]] : { ...(cur[t] ?? {}) };
    cur = cur[t];
  });
  return root;
}

export function applyMessage(state: Surfaces, msg: A2uiMessage): Surfaces {
  if ("createSurface" in msg) {
    const { surfaceId, catalogId, theme } = msg.createSurface;
    return { ...state, [surfaceId]: { surfaceId, catalogId, variant: theme?.variant, components: {}, data: {} } };
  }
  if ("updateComponents" in msg) {
    const s = state[msg.updateComponents.surfaceId];
    if (!s) return state;
    const components = { ...s.components };
    for (const c of msg.updateComponents.components) if (c?.id && c.component) components[c.id] = c;
    return { ...state, [s.surfaceId]: { ...s, components } };
  }
  if ("updateDataModel" in msg) {
    const { surfaceId, path, value } = msg.updateDataModel;
    const s = state[surfaceId];
    return s ? { ...state, [surfaceId]: { ...s, data: setPointer(s.data, path, value) } } : state;
  }
  if ("deleteSurface" in msg) {
    const { [msg.deleteSurface.surfaceId]: _gone, ...rest } = state;
    return rest;
  }
  return state; // unknown message kinds are ignored
}

export const buildSurfaces = (messages: A2uiMessage[]): Surfaces => messages.reduce(applyMessage, {} as Surfaces);

/** A surface can be drawn once its `root` component exists and it targets a catalog we know. */
export const renderable = (s: Surface | undefined): s is Surface => Boolean(s && s.components.root && s.catalogId === CATALOG_ID);

/** Resolves a Dynamic* value: a literal, or {path} bound into the data model. */
export function resolve<T = unknown>(value: unknown, data: unknown): T | undefined {
  if (value && typeof value === "object" && !Array.isArray(value) && typeof (value as any).path === "string" && Object.keys(value).length === 1) {
    return getPointer(data, (value as any).path) as T | undefined;
  }
  return value as T | undefined;
}
