FROM node:22-alpine AS deps
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /web
# Next.js embute variáveis NEXT_PUBLIC_* no build: trocar de domínio exige rebuild.
# API_UPSTREAM (ex.: http://webhook-api:8000) grava o proxy no build. Com
# NEXT_PUBLIC_API_BASE_URL vazio, o browser chama o próprio painel.
ARG NEXT_PUBLIC_API_BASE_URL
ARG API_UPSTREAM=
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
# Vazio no build = o browser não fala com o Sentry. O DSN do servidor é runtime.
ARG NEXT_PUBLIC_SENTRY_DSN=
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    API_UPSTREAM=$API_UPSTREAM \
    NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY \
    NEXT_PUBLIC_SENTRY_DSN=$NEXT_PUBLIC_SENTRY_DSN \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /web/node_modules ./node_modules
COPY web ./
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /web
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S web && adduser -S web -G web
COPY --from=build --chown=web:web /web/.next/standalone ./
COPY --from=build --chown=web:web /web/.next/static ./.next/static
COPY --from=build --chown=web:web /web/public ./public
USER web
EXPOSE 3000
CMD ["node", "server.js"]
