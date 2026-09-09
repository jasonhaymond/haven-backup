# Haven Backup Portal -- frontend

React + Vite + Tailwind SPA for the Haven Backup portal. See the repo root
[README.md](../README.md) and [docs/](../docs/) for what this is and how to
run the whole stack.

```bash
npm install
npm run dev      # http://localhost:5173, proxies /api to http://localhost:8000
npm run build    # outputs dist/, served by frontend/Dockerfile's Caddy stage in production
```
