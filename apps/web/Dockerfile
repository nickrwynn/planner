FROM node:20-bookworm-slim

WORKDIR /app

# Enable pnpm via corepack
RUN corepack enable

# Copy workspace manifests
COPY package.json pnpm-workspace.yaml turbo.json /app/
COPY apps/web/package.json /app/apps/web/package.json

RUN pnpm install --frozen-lockfile=false

COPY apps/web /app/apps/web

WORKDIR /app/apps/web

RUN pnpm exec next build

EXPOSE 3000

CMD ["pnpm", "exec", "next", "start", "-H", "0.0.0.0", "-p", "3000"]

