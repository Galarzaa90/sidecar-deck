import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const backendUrl = loadEnv(mode, '.', '').SIDECAR_DECK_BACKEND_URL || 'http://localhost:8080';
  const websocketUrl = backendUrl.replace(/^http/, 'ws');

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        '/api': backendUrl,
        '/health': backendUrl,
        '/ws': {
          target: websocketUrl,
          ws: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
    },
  };
});
