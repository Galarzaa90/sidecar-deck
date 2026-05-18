# Sidecar Deck Frontend

React/Vite dashboard optimized for a `1920x480` kiosk display. During development, Vite proxies API, health, and WebSocket traffic to the backend on `localhost:8080`.

## Local Setup

```bash
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

## Scripts

```bash
npm run dev
npm run build
npm run preview
```

`npm run build` type-checks with TypeScript and writes the production app to `dist`.

## Backend Proxy

The Vite dev server proxies:

- `/api` to `http://localhost:8080`
- `/health` to `http://localhost:8080`
- `/ws` to `ws://localhost:8080`

Start the backend and agent before using the local dashboard if you want live metrics.

## Docker

From the repository root:

```bash
docker build -t sidecar-deck-frontend -f frontend/Dockerfile .
docker run --rm -p 8081:8080 -e BACKEND_URL=http://host.docker.internal:8080 sidecar-deck-frontend
```

The image serves the built app through nginx and proxies same-origin API/WebSocket traffic to `BACKEND_URL`.
