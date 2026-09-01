import { copyFileSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath, URL } from 'node:url';
import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

// Single source of truth for the version shown in the footer
const { version } = createRequire(import.meta.url)('./package.json');

// The WAF question set is canonical at repo-root `/data` so the backend agent
// and the frontend read one file. Vite only serves `public/`, so copy it in for
// both dev and build. `public/data` is generated (git-ignored) - never edit it.
const syncCanonicalData = (): Plugin => {
  const src = fileURLToPath(new URL('../data/waf-data.json', import.meta.url));
  const destDir = fileURLToPath(new URL('./public/data', import.meta.url));
  const copy = () => {
    mkdirSync(destDir, { recursive: true });
    copyFileSync(src, `${destDir}/waf-data.json`);
  };
  return {
    name: 'sync-canonical-data',
    buildStart: copy,
    configureServer: copy,
  };
};

// Deployed to GitHub Pages, which may serve the app from a subdirectory.
// Relative asset URLs keep the build portable across both cases.
export default defineConfig({
  base: './',

  define: {
    __APP_VERSION__: JSON.stringify(version),
  },

  // Production serves the frontend and the API from one origin, so the client
  // calls relative `/api` paths (see src/store/api.ts). Under `yarn dev` Vite
  // only serves static assets, so proxy `/api` to the locally-running Flask
  // backend (backend/server, default port 8000) to exercise the full stack.
  // Override the target with VITE_API_PROXY when the backend runs elsewhere.
  server: {
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },

  plugins: [
    syncCanonicalData(),

    react({
      jsxImportSource: '@emotion/react',
      babel: {
        plugins: ['@emotion/babel-plugin'],
      },
    }),

    VitePWA({
      registerType: 'autoUpdate',
      // Every PNG has to be precached exactly once. The plugin already
      // precaches whatever `manifest.icons` lists, so `globPatterns` below
      // deliberately does not match PNGs: a file reached both ways lands in the
      // precache manifest twice with different revisions, which makes Workbox
      // throw while the worker is evaluating - and the worker then never
      // registers, silently costing all offline support.
      //
      // So the PNGs that are *not* manifest icons are listed here, including
      // logo-waf.svg, which sits under icons/ but is not a manifest icon.
      includeAssets: ['assets/images/*.png', 'assets/icons/logo-waf.svg'],
      manifest: {
        name: 'Databricks WAF Assessment',
        short_name: 'WAF Assessment',
        description: 'Databricks Well Architected Framework Assessment Tool',
        theme_color: '#FF3621',
        background_color: '#ffffff',
        display: 'standalone',
        start_url: './',
        scope: './',
        icons: [72, 96, 128, 144, 152, 192, 384, 512].map((size) => ({
          src: `assets/icons/icon-${size}x${size}.png`,
          sizes: `${size}x${size}`,
          type: 'image/png',
          purpose: 'any maskable',
        })),
      },
      workbox: {
        // The WAF question sets are large; raise the precache size ceiling
        maximumFileSizeToCacheInBytes: 6 * 1024 * 1024,
        // No `png` here on purpose - see the note on `includeAssets` above
        globPatterns: ['**/*.{js,css,html,json,webmanifest}'],

        // Inline the Workbox runtime into sw.js rather than loading it as a
        // separate chunk, so the worker is a single self-contained script.
        inlineWorkboxRuntime: true,
      },
    }),
  ],

  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },

  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
