FROM node:26-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
COPY design-system/package.json design-system/
COPY admin/package.json admin/
RUN npm ci --workspace admin --include-workspace-root
COPY design-system design-system
COPY admin admin
ARG VITE_API_URL=""
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run --workspace admin build

FROM nginx:alpine AS runtime
COPY admin/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/admin/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
