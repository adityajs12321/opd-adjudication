# Deployment Guide

Three pieces: **Neo4j AuraDB** (graph), **Render** (FastAPI backend + Postgres), **Vercel** (Next.js frontend).
Deploy in that order — the backend needs the AuraDB credentials, and the frontend needs the backend URL.

---

## 1. Neo4j AuraDB (graph database)

1. Go to [console.neo4j.io](https://console.neo4j.io) → **Create instance** → **AuraDB Free**.
2. When it provisions, **download the credentials file** (the password is shown only once).
3. Note these three values:
   - `NEO4J_URI` → looks like `neo4j+s://xxxxxxxx.databases.neo4j.io` (use the `neo4j+s://` scheme — it's encrypted)
   - `NEO4J_USER` → `neo4j`
   - `NEO4J_PASSWORD` → from the credentials file

The graph is built automatically on backend startup (`init_graph`), so there's nothing to seed manually.

---

## 2. Render (backend + Postgres)

The repo includes `render.yaml`, so you can deploy as a **Blueprint**:

1. Push the repo to GitHub (see step 4 below if not pushed yet).
2. In Render → **New → Blueprint** → connect the `medical-docs` repo.
3. Render reads `render.yaml` and creates:
   - `plum-opd-backend` (web service, root dir `backend/`)
   - `plum-opd-db` (free Postgres — `DATABASE_URL` is wired in automatically)
4. Before the first deploy finishes, set the secret env vars (marked `sync: false`) in the
   backend service → **Environment**:
   - `GEMINI_API_KEY`
   - `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` (from step 1)
   - `FRONTEND_URLS` → leave blank for now; fill in after Vercel (step 3)
5. Deploy. Confirm it's up at `https://plum-opd-backend.onrender.com/health` → `{"status":"ok"}`.

Note: the free tier spins down on inactivity. The first request after idle is slow (~30s cold start),
and each cold start rebuilds the policy graph in AuraDB (idempotent, safe).

---

## 3. Vercel (frontend)

1. In Vercel → **Add New → Project** → import the `medical-docs` repo.
2. Framework preset: **Next.js** (auto-detected). Root directory: repo root (default).
3. Add an environment variable:
   - `NEXT_PUBLIC_API_URL` = `https://plum-opd-backend.onrender.com` (your Render URL, no trailing slash)
4. Deploy. Note the resulting URL, e.g. `https://your-app.vercel.app`.
5. **Go back to Render** → backend → Environment → set `FRONTEND_URLS` to the Vercel URL
   (e.g. `https://your-app.vercel.app`) and save. This triggers a redeploy and unblocks CORS.

For preview deployments, `FRONTEND_URLS` accepts a comma-separated list.

---

## 4. Push to GitHub (if needed)

```bash
git add .
git commit -m "Add deployment config"
git push origin main
```

Render and Vercel auto-redeploy on every push to `main`.

---

## Environment variable summary

| Variable | Where | Value |
|---|---|---|
| `GEMINI_API_KEY` | Render | Your Gemini API key |
| `DATABASE_URL` | Render | Auto-wired from `plum-opd-db` |
| `NEO4J_URI` | Render | `neo4j+s://...databases.neo4j.io` |
| `NEO4J_USER` | Render | `neo4j` |
| `NEO4J_PASSWORD` | Render | From AuraDB credentials |
| `FRONTEND_URLS` | Render | Vercel URL(s), comma-separated |
| `NEXT_PUBLIC_API_URL` | Vercel | Render backend URL |
