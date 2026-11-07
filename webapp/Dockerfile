# Builder: bake VITE_API_URL at build time.
#   - Same-origin (composed nginx proxy): leave empty (default).
#   - Standalone webapp (Vercel/Netlify/own host): pass the api origin,
#     e.g. --build-arg VITE_API_URL=https://graduator-api.example.com
FROM node:22-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . ./
ARG VITE_API_URL=""
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

FROM nginx:alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
