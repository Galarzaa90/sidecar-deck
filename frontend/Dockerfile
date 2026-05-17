FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine
ENV BACKEND_URL=http://backend:8080 \
    NGINX_PORT=8080 \
    NGINX_ENVSUBST_FILTER="^(BACKEND_URL|NGINX_PORT)$"
COPY frontend/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
