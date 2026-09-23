# --- build ---
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Vite inlines VITE_* at build time, so the key must be present here rather than
# at container start. Empty is fine: the map falls back to keyless OSM tiles.
ARG VITE_MAPTILER_KEY=""
ENV VITE_MAPTILER_KEY=$VITE_MAPTILER_KEY
RUN npm run build

# --- serve ---
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY security-headers.conf /etc/nginx/security-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
