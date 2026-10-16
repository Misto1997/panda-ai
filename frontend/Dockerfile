# Context: frontend/   docker build --build-arg NEXT_PUBLIC_FIREBASE_API_KEY=... frontend
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Public Firebase web config is inlined into the browser bundle at build time (these values are not secrets).
ARG NEXT_PUBLIC_FIREBASE_API_KEY
ARG NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN
ARG NEXT_PUBLIC_FIREBASE_PROJECT_ID
ARG NEXT_PUBLIC_FIREBASE_APP_ID
# Deployed builds set REQUIRE_FIREBASE=true so the app can never ship with auth silently disabled.
ARG REQUIRE_FIREBASE=false
ENV NEXT_PUBLIC_FIREBASE_API_KEY=$NEXT_PUBLIC_FIREBASE_API_KEY \
    NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=$NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN \
    NEXT_PUBLIC_FIREBASE_PROJECT_ID=$NEXT_PUBLIC_FIREBASE_PROJECT_ID \
    NEXT_PUBLIC_FIREBASE_APP_ID=$NEXT_PUBLIC_FIREBASE_APP_ID \
    NEXT_TELEMETRY_DISABLED=1
RUN if [ "$REQUIRE_FIREBASE" = "true" ]; then \
      for v in NEXT_PUBLIC_FIREBASE_API_KEY NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN NEXT_PUBLIC_FIREBASE_PROJECT_ID NEXT_PUBLIC_FIREBASE_APP_ID; do \
        eval "val=\$$v"; \
        if [ -z "$val" ]; then echo "ERROR: REQUIRE_FIREBASE=true but build arg $v is empty; refusing to build without auth." >&2; exit 1; fi; \
      done; \
    fi
RUN mkdir -p public && npm run build

FROM node:24-alpine AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=8080 HOSTNAME=0.0.0.0
# Cloud Run reuses idle connections for up to 10 min; Next standalone server.js reads KEEP_ALIVE_TIMEOUT (ms).
ENV KEEP_ALIVE_TIMEOUT=620000
# Runtime env: GATEWAY_URL (the API's Cloud Run URL), read by the BFF routes on each request.
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
USER node
CMD ["node", "server.js"]
