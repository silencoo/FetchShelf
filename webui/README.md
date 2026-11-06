# FetchShelf WebUI frontend

This directory is the source for the WebUI served at `/ui`. Vite writes the production bundle to `../src/webui/static`, which remains committed so the Python application can run without Node.

```bash
npm ci --prefix webui
npm run build --prefix webui
```

For local development, keep the Python WebUI server running on port `5555`, then start Vite. Its development proxy forwards the existing REST and WebSocket routes.

```bash
npm run dev --prefix webui
```

The interface uses the official Magic UI registry source for `@magicui/grid-pattern` and `@magicui/number-ticker`. Product controls and data-heavy views use project-owned HTML/CSS so their behavior remains stable. The existing browser workflows live in `webui/src/legacy/app.js`; Vite bundles that module alongside the React-powered visual components.

The immersive feed (`src/feed/`) is a separate React app loaded on first use, in its own chunk. It takes over the whole viewport and keeps playback in `player.ts`: a small pool of recycled `<video>` elements, because iOS only allows audible playback on an element that has started inside a user gesture. Don't replace the pool with one element per slide, or sound stops at every swipe.
