# Deploying to Railway

The web app is a thin HTTP wrapper over the same `extract → analyze → render` pipeline the
CLI uses. It ships as a Docker image; Railway builds it from [`Dockerfile`](Dockerfile) using
the settings in [`railway.json`](railway.json).

---

## Before you start — rotate the key

The key currently in `.env` was pasted in plaintext, so treat it as compromised.

1. Go to **console.anthropic.com → Settings → API keys**
2. Create a new key, and **delete the old one**
3. Use the new key everywhere below

`.env` is gitignored and `.dockerignore`d, so it is never committed and never enters the
image. The key reaches production **only** as a Railway environment variable.

---

## 1. Push the repo

Railway deploys from a Git remote.

```bash
git init                      # if you have not already
git add -A
git commit -m "deck-onepager: CLI, one-page renderer, and web app"
git branch -M main
git remote add origin git@github.com:<you>/deck-onepager.git
git push -u origin main
```

Confirm the key did not go with it:

```bash
git ls-files | grep -c '^\.env$'    # must print 0
```

## 2. Create the service

```bash
npm i -g @railway/cli     # or: brew install railway
railway login
railway init              # name the project, e.g. deck-onepager
railway link              # if the project already exists
```

Or use the dashboard: **New Project → Deploy from GitHub repo**.

## 3. Set the environment variables

```bash
railway variables --set "ANTHROPIC_API_KEY=sk-ant-api03-YOUR-NEW-KEY"
railway variables --set "ANTHROPIC_MODEL=claude-opus-5"
railway variables --set "APP_PASSWORD=pick-a-long-random-passphrase"
```

| Variable | Required | Default | Notes |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | **yes** | — | `/healthz` returns 503 without it |
| `ANTHROPIC_MODEL` | no | `claude-opus-5` | |
| `APP_PASSWORD` | **strongly recommended** | unset | Unset = the URL is public and **anyone can spend your API credit** |
| `MAX_UPLOAD_MB` | no | `64` | Image-heavy decks run 50 MB+ |
| `JOB_TTL_MINUTES` | no | `60` | How long a finished PDF stays in memory |
| `PORT` | no | injected | Railway sets this; the container reads it |

## 4. Deploy

```bash
railway up
railway domain        # generates a public URL
```

## 5. Verify

```bash
curl https://<your-app>.up.railway.app/healthz
# ok version=0.1.0 model=claude-opus-5 api_key=set
```

Then open the URL, enter any username and your `APP_PASSWORD` at the browser prompt, and
upload a deck.

---

## What you get

| Route | Auth | Purpose |
|---|---|---|
| `GET /` | gated | Upload page |
| `GET /healthz` | **open** | Health check — Railway needs this ungated |
| `POST /api/jobs` | gated | Upload a deck → `202` + job id |
| `GET /api/jobs/{id}` | gated | Poll status and progress |
| `GET /api/jobs/{id}/pdf` | gated | Download the one-pager |
| `GET /api/jobs/{id}/json` | gated | Download the analysis JSON |
| `GET /api/template.pdf` | gated | The blank document template |
| `GET /api/docs` | gated | OpenAPI docs |

An analysis takes **50–90 seconds**, which is why uploads create a background job and the
page polls rather than holding the request open.

---

## Operational notes

**Jobs live in memory, in one process.** `railway.json` pins `numReplicas: 1` and the
container runs `--workers 1`. Scaling to more replicas or workers would send a poll to a
process that has never heard of the job. To scale out you would need shared storage (Redis
or a volume) for the job store.

**A restart loses in-flight jobs.** Deploys and crashes drop queued and running work. Results
already downloaded are unaffected; anything mid-flight must be re-uploaded.

**Cost is per analysis.** Roughly **$0.14–$0.20** per deck at Claude Opus 5 list pricing
(measured: 12-slide PPTX ≈ $0.14, 30-page PDF ≈ $0.20, 8-page scanned PDF ≈ $0.16). Every
completed job reports its own token count and cost. This is exactly why `APP_PASSWORD`
matters — without it, a public URL is an open tap on your API account.

**Nothing is persisted.** Uploads are written to a temp directory that is deleted when the
job ends; results are held in memory until the TTL expires. There is no database and no
object storage.

**Legacy `.ppt` and image-only `.pptx` need LibreOffice.** The Dockerfile has the
`apt-get install libreoffice-impress` line commented out because it adds ~450 MB. Uncomment
it if you need those formats. `.pdf` and text-bearing `.pptx` work without it, and the app
degrades with a clear message rather than failing obscurely.

**Memory.** Rasterizing a large image-only PDF is the peak. The 512 MB Railway starter tier
is enough for typical decks; bump it if you see OOM restarts on big scanned files.

---

## Running it locally

```bash
python -m pip install -e ".[dev,web]"
cp .env.example .env          # then set ANTHROPIC_API_KEY
uvicorn onepager.web.app:app --reload --port 8000
```

Open <http://127.0.0.1:8000>. With `APP_PASSWORD` unset there is no login prompt — fine on
localhost, never in production.
