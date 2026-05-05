import { defineConfig, loadEnv, type ProxyOptions } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * Two dev modes:
 *
 *   • local  (default) — proxy /api → http://localhost:8000  (run `make dev-backend` separately)
 *   • remote          — proxy /api → ${VITE_REMOTE_BACKEND_URL}, with
 *                       Authorization: Bearer ${DATABRICKS_TOKEN} injected.
 *
 * Switch with: `VITE_BACKEND_MODE=remote npm run dev` (or `npm run dev:remote`).
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, '');
  const backendMode = env.VITE_BACKEND_MODE ?? 'local';

  let proxy: Record<string, ProxyOptions>;
  if (backendMode === 'remote') {
    const target = env.VITE_REMOTE_BACKEND_URL;
    if (!target) {
      throw new Error(
        'VITE_BACKEND_MODE=remote requires VITE_REMOTE_BACKEND_URL ' +
          '(e.g. https://sales-dashboard-flask-1234.5.azure.databricksapps.com).',
      );
    }
    const token = env.DATABRICKS_TOKEN;
    if (!token) {
      throw new Error(
        'VITE_BACKEND_MODE=remote requires DATABRICKS_TOKEN. ' +
          'Run: export DATABRICKS_TOKEN=$(databricks auth token -p dev | jq -r .access_token)',
      );
    }
    proxy = {
      '/api': {
        target,
        changeOrigin: true,
        secure: true,
        configure: (httpProxy) => {
          httpProxy.on('proxyReq', (proxyReq) => {
            proxyReq.setHeader('Authorization', `Bearer ${token}`);
          });
        },
      },
    };
  } else {
    proxy = {
      '/api': {
        target: env.VITE_LOCAL_BACKEND_URL ?? 'http://localhost:8000',
        changeOrigin: false,
      },
    };
  }

  return {
    root: __dirname,
    plugins: [react()],
    build: {
      outDir: resolve(__dirname, 'dist'),
      emptyOutDir: true,
      sourcemap: true,
    },
    server: {
      host: '0.0.0.0',
      port: Number(env.VITE_PORT ?? 5173),
      strictPort: true,
      proxy,
    },
    preview: {
      host: '0.0.0.0',
      port: Number(env.VITE_PORT ?? 5173),
    },
  };
});
