# Deploying the Sports Analytics Backend

The production portfolio currently falls back to an embedded demo engine.
Deploying this FastAPI backend gives the live site the **real** pipeline:
LangGraph → deterministic SQL → PostgreSQL with the full FIFA World Cup 2022 +
NFL Big Data Bowl datasets.

Everything below is already prepared — `render.yaml` (repo root), the slim
`python-backend/requirements-deploy.txt` (no torch/faiss; retrieval degrades
gracefully to BM25-only, verified working), and env-var-driven ETL scripts.

## One-time manual steps (account owner)

### 1. Push this repo to GitHub

```bash
gh auth login          # one-time browser flow
git push origin main
```

### 2. Create the Render Blueprint

1. Go to https://dashboard.render.com → **New** → **Blueprint**
2. Connect the `shubhampareek1211/codeagent` repo
3. Render reads `render.yaml` and creates:
   - `sports-analytics-backend` (free web service, slim Python build)
   - `sports-analytics-db` (free PostgreSQL, wired in via `SPORTS_DATABASE_URL`)
4. Click **Apply** and wait for the first deploy (it will be healthy but the DB
   is empty at this point)

> Note: Render's free PostgreSQL expires after 30 days. For something
> permanent, create a free [Neon](https://neon.tech) database instead, then set
> `SPORTS_DATABASE_URL` on the Render service manually to the Neon URL.

### 3. Load the data (from this machine)

Copy the **External Database URL** from the Render dashboard (or Neon), then:

```bash
cd python-backend
export SPORTS_DATABASE_URL="<external database url>"
.venv/bin/python etl/run_migration.py      # base schema + extensions + indexes
.venv/bin/python etl/statsbomb_etl.py      # FIFA World Cup 2022 (~2 min)
.venv/bin/python etl/nfl_etl.py            # NFL Big Data Bowl week 1
.venv/bin/python etl/wellness_seed.py      # synthetic wellness scores
```

Verify:

```bash
curl https://sports-analytics-backend.onrender.com/health
curl -X POST https://sports-analytics-backend.onrender.com/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Top 5 Argentine players by total distance"}'
```

### 4. Point Vercel at the live backend

```bash
cd "/Users/shubhampareek/Desktop/Code Agents"
vercel env add SPORTS_ANALYTICS_BACKEND_URL production
# paste: https://sports-analytics-backend.onrender.com
vercel --prod --yes
```

The proxy route immediately switches from the embedded demo engine to the real
backend. If the backend is ever unreachable, it still falls back gracefully.

## Notes

- **Memory:** the slim build (BM25-only retrieval) was verified locally end to
  end and uses well under 512 MB. Do NOT use `requirements.txt` for deploys —
  torch alone will OOM the free tier.
- **Cold starts:** Render free services sleep after 15 min idle; the first
  request takes ~30 s. The Vercel route's 8 s health / 15 s query timeouts mean
  the very first visitor after idle may see the demo-engine fallback, and the
  next request hits the live backend. Acceptable for a portfolio; upgrade the
  service if it matters.
- **CORS** is preconfigured for `shubham-pareek-portfolio.vercel.app` in
  `render.yaml`.
