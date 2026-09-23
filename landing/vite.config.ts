// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

// GitHub Pages serves project sites under a repo sub-path, e.g. theroverse.github.io/athena/.
// Vite's `base` rewrites every emitted asset URL, and the router `basepath` (see src/router.tsx)
// keeps client navigation in sync with it. Both are derived from the same value.
const BASE_PATH = "/athena/";

export default defineConfig({
  vite: {
    base: BASE_PATH,
  },
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
    // Static-site generation: render every route to HTML at build time so the output can be
    // served as plain files by GitHub Pages (no Node runtime). crawlLinks picks up internal links.
    prerender: { enabled: true, crawlLinks: true },
  },
  // Skip Nitro: its own prerenderer doesn't resolve TanStack Start's route handler here
  // (returns 404). TanStack Start's built-in prerenderer above emits the static pages into
  // dist/client, which is the directory we publish to GitHub Pages.
  nitro: false,
});
