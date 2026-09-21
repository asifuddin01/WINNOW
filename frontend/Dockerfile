# syntax=docker/dockerfile:1
# Winnow web image. Targets: `dev` (Vite dev server) and `prod` (static build served by Caddy).

FROM node:22-alpine AS base
# COREPACK_HOME outside /root, so the non-root dev user can run the pinned pnpm offline.
ENV PNPM_HOME=/pnpm \
    COREPACK_HOME=/opt/corepack \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    CI=true
ENV PATH=$PNPM_HOME:$PATH
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN corepack install && chmod -R a+rX /opt/corepack
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm config set store-dir /pnpm/store && pnpm install --frozen-lockfile

FROM base AS dev
COPY . .
RUN chown -R node:node /app
USER node
EXPOSE 5173
CMD ["pnpm", "exec", "vite", "--host", "0.0.0.0"]

FROM base AS build
COPY . .
RUN pnpm run build

FROM caddy:2-alpine AS prod
COPY docker/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
EXPOSE 8080
