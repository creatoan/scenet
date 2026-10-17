import { defineConfig } from "vite";

/**
 * The playground build.
 *
 * `base` is relative, because one build is served from several places: `/` under
 * `npm run dev`, and on GitHub Pages both `/scenet/playground/` and the release's own
 * `/scenet/vX.Y/playground/` -- a release's site is built once and served unchanged at
 * both. Relative, "all generated URLs [are] relative to each file" (Vite's docs), and
 * every asset the app fetches itself is resolved against `document.baseURI`, so nothing
 * here knows where it is served from.
 */
export default defineConfig({
  base: "./",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    // Monaco is large and splits into many chunks. The default 500 kB warning fires on
    // every build and says nothing useful about a page that also ships a Python
    // interpreter.
    chunkSizeWarningLimit: 4000,
  },
  worker: {
    format: "es",
  },
  optimizeDeps: {
    // The YAML worker imports `path-browserify`, which is CommonJS. In development Vite
    // serves a `?worker` entry module by module, and it only pre-bundles a dependency
    // it discovers from application code: an import made from inside node_modules is
    // assumed to have been bundled along with its parent, which a worker entry never
    // is. So the browser received raw CommonJS, the worker died on `module is not
    // defined`, and schema validation, completion and hover vanished in `npm run dev`
    // only -- a production build bundles the worker and was never affected.
    //
    // Every other import of `monaco-yaml/yaml.worker` resolves to an ES module today.
    // If a monaco-yaml update adds another CommonJS one, it belongs here too.
    include: ["monaco-yaml > path-browserify"],
    // Pyodide loads its own WebAssembly and looks for sibling files at runtime. Letting
    // Vite pre-bundle it rewrites those paths and it stops finding them.
    exclude: ["pyodide"],
  },
  server: {
    headers: {
      // Not required by Pyodide today, but these are what let it use SharedArrayBuffer
      // if a future version wants to, and they cost nothing in development.
      "Cross-Origin-Opener-Policy": "same-origin",
      "Cross-Origin-Embedder-Policy": "credentialless",
    },
  },
});
