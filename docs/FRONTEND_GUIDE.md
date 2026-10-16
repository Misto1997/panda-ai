# Frontend guide

`frontend/` is a **Next.js 15 + React 19 + TypeScript** app: the browser UI plus a thin server-side layer (the BFF). Plain CSS, no UI framework.

**Why a BFF:** the browser never needs the gateway's address; the BFF forwards the Firebase `Authorization` header; no CORS in production (the browser talks only to its own origin). It is a pass-through (`lib/gateway.ts`); `GATEWAY_URL` is read at request time. Next.js `standalone` output gives a small container for Cloud Run.

## Request flow

```
browser (page.tsx) -- POST /api/chat --> Next.js route handler --> FastAPI /api/chat
        ^                                                              |
        '------- AG-UI stream: RUN_STARTED, STEP_*, TEXT_MESSAGE_*, ACTIVITY_SNAPSHOT, CUSTOM, RUN_FINISHED -----'
```

`lib/sse.ts` is an AG-UI client (parses `data: {json}` events). `panda.step` events drive the stepper; `ACTIVITY_SNAPSHOT` (`a2ui-surface`) carries the answer surface; `CUSTOM panda.result` carries the whole result. The answer shows as soon as data is ready and is replaced in place when the model-written insight arrives (`meta.narrated`).

## UI structure

| Area | Files | Behaviour |
|---|---|---|
| Page | `app/page.tsx` | chat state, streaming, input, per-turn rendering |
| Sidebar | `components/Sidebar.tsx` | New chat, collapsible rail, chat history (from `/api/threads`, with relative times, open and delete), Options popover (force raw table scan, bypass semantic cache), collapsible Runtime footer (active profile and backends from `/api/meta`) |
| Empty state | `components/EmptyState.tsx`, `lib/suggestions.ts` | capability cards and example chips; static fallback if `/api/meta` is down |
| Stepper | `components/Stepper.tsx` | live stage list with elapsed seconds, from running and finished `panda.step` events (understanding, writing SQL, running, preparing, investigating, writing insights, checking the previous answer) |
| Answer | `components/a2ui/`, `components/blocks.tsx` | A2UI renderer and its React components |
| Answer actions | `components/AnswerActions.tsx`, `lib/feedback.ts`, `lib/clipboard.ts` | thumbs up/down with reason pills (up: Correct, Useful, Clear; down: Wrong answer, Wrong data, Wrong period, Too slow, Bad chart, Missed my question, Other; up to 5) and an optional 240-char comment, plus copy answer (text and table). Feedback errors are inline and never touch the answer |
| SQL card | `blocks.tsx` `SqlBlock`, `lib/sql.ts` | collapsible "Generated SQL" with light highlighting, pretty line breaks and Copy |
| RCA surface | `blocks.tsx` | `VerdictHeader` (metric, delta, current vs baseline, polarity-aware good/bad tone), `Callouts` (fired preflight checks), `DecompositionTable`, `SegmentBars`, `HypothesisList`, then the analyst summary |
| Fallback | `components/ResultView.tsx` | renders `panda.result` with the same blocks when no surface arrives or it fails to render, so the page is never blank |
| Auth | `components/AuthProvider.tsx`, `lib/firebase.ts`, `lib/quota.ts` | Firebase Google sign-in, enabled only when all four `NEXT_PUBLIC_FIREBASE_*` values are set; top-bar "N / limit questions left today" from `/api/me` |

A2UI catalog components: Column, Grid, Heading, Text, BulletList, Callouts, KpiRow, VerdictHeader, VegaLiteChart, DataTable, HypothesisList, DecompositionTable, SegmentBars, ChipRow, SuggestionChips, SqlBlock. `components/a2ui/catalog.json` is a copy of `backend/app/presentation/a2ui_catalog.json`; keep them in sync. `SuggestionChips` ask the suggested question when clicked.

## BFF routes (`app/api/`)

| Route | Forwards to |
|---|---|
| `chat` | `POST /api/chat` (streams the response back) |
| `meta`, `me` | runtime info; remaining quota |
| `threads`, `threads/[id]` | history list; open and delete one chat |
| `feedback`, `threads/[id]/feedback` | submit a rating; restore thumb states |

History is stored per user on the server (30 days, 50 chats).

## Files

| File | Role |
|---|---|
| `package.json`, `package-lock.json` | dependencies and scripts (`dev`, `build`, `start`); commit the lock file |
| `tsconfig.json` | `strict`, `@/*` alias to the project root |
| `next.config.mjs` | `output: "standalone"`, `devIndicators: false` |
| `app/layout.tsx`, `app/globals.css` | HTML shell and all styling |
| `components/Chart.tsx` | Vega-Lite via `vega-embed` (client only) |
| `components/Markdown.tsx` | small safe renderer for bold, code and bullets; never injects raw HTML |
| `lib/types.ts` | mirror of backend payloads (`schemas/chat.py`, `rca/models.py`); change all three together |
| `lib/format.ts` | number, currency, percent formatting |
| `Dockerfile` | build args `NEXT_PUBLIC_FIREBASE_*` (inlined at build time) and `REQUIRE_FIREBASE=true` for deployed builds, which fails the build if any value is empty |

## Run and change

```bash
make web                                  # dev server on :3000 with hot reload
make typecheck                            # tsc --noEmit
GATEWAY_URL=http://host:8000 make web     # another gateway
```

When a backend payload changes, update `lib/types.ts` first; the compiler then lists every place to fix. AG-UI and A2UI are open, pre-1.0 specs, so each side keeps the contract in one small adapter.
