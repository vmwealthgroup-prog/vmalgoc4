# Troubleshooting
**`GET /api/app/config 404`, Register fails with 404, or the app says "Cannot reach the API".** The web app cannot find the API. Start it (`cd backend && uvicorn app.main:app --port 8000`).
If the API runs elsewhere, set `API_INTERNAL_URL` for the web server (for example `API_INTERNAL_URL=http://127.0.0.1:9000 npm run dev`), or set `NEXT_PUBLIC_API_URL` to call it directly (then add the web origin to `CORS_ORIGINS`).

**Browser reports CORS errors from the deployed frontend to the API.** Set `CORS_ORIGINS` on the API host to the exact frontend origin, with no trailing slash. For this deployment use `https://vmalgoc4-henna.vercel.app`. If there are multiple domains, comma-separate them, for example `https://vmalgoc4-henna.vercel.app,https://your-custom-domain.example`. Redeploy/restart the API after changing the setting. Do not use `*` when credentials are enabled.

**Browser shows `Invariant: Missing ActionQueueContext`, a hydration error "in <#document>", or the dev server prints `Cannot find module './NNN.js'`.**
