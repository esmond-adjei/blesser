# Build context is the repo root: the site depends on the design-system workspace.
FROM node:26-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json ./
COPY design-system/package.json design-system/
COPY site/package.json site/
RUN npm ci --workspace site --include-workspace-root

COPY design-system design-system
COPY site site
RUN npm run --workspace site build

FROM node:26-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production HOST=0.0.0.0 PORT=4321

COPY package.json package-lock.json ./
COPY design-system/package.json design-system/
COPY site/package.json site/
RUN npm ci --workspace site --include-workspace-root --omit=dev && npm cache clean --force

COPY design-system design-system
COPY --from=builder /app/site/dist site/dist

USER node
EXPOSE 4321
CMD ["node", "site/dist/server/entry.mjs"]
