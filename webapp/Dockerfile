# Builder: bake VITE_API_URL at build time.
#   - Same-origin (the compose nginx proxy): leave empty (default).
#   - Standalone host: pass the API origin,
#     e.g. --build-arg VITE_API_URL=https://api.example.com
FROM node:26-alpine AS builder

# Build context is the repo root: the app depends on the design-system workspace.
WORKDIR /app

COPY package.json package-lock.json ./
COPY design-system/package.json design-system/
COPY webapp/package.json webapp/
RUN npm ci --workspace webapp --include-workspace-root

COPY design-system design-system
COPY webapp webapp
ARG VITE_API_URL=""
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run --workspace webapp build

FROM nginx:alpine AS runtime

COPY webapp/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/webapp/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
