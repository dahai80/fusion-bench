import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// issue #23: dev server 11474 (architecture/port-registry.yaml). Proxies the
// bench API surface to the REST server on 11467 so standalone mode mirrors
// the embedded gateway /shell/fusion-bench/ layout (same-origin).
// FUSION_DEV_BACKEND / FUSION_BENCH_WEB_PORT override for parity.
const backend = process.env.FUSION_DEV_BACKEND ?? 'http://127.0.0.1:11467';
const port = Number(process.env.FUSION_BENCH_WEB_PORT ?? 11474);

const apiPaths = ['/api', '/health', '/ready'];

export default defineConfig({
    plugins: [react()],
    // Embedded deployment serves dist through the gateway sub-path
    // /shell/fusion-bench/ — relative base + hash router works in both
    // embedded and standalone modes.
    base: './',
    server: {
        port,
        strictPort: true,
        proxy: Object.fromEntries(
            apiPaths.map((p) => [p, { target: backend, changeOrigin: true }])
        ),
    },
    preview: {
        port,
        strictPort: true,
        proxy: Object.fromEntries(
            apiPaths.map((p) => [p, { target: backend, changeOrigin: true }])
        ),
    },
    envPrefix: ['VITE_', 'FUSION_'],
});
