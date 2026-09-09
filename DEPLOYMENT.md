# Deploying the Owner Analytics application to Streamlit Community Cloud

The complete existing product, presented through Streamlit. The deterministic engine is unchanged
and remains the only calculation authority; `streamlit_app.py` and everything under `owner_app/`
render projections it produces and compute nothing.

    Evidence -> Validation -> Semantic Layer -> Trust Gate -> Metric Engine -> Analytics Engine
    -> Business Insight Engine -> Answer Contract -> AI Business Analyst -> Streamlit UI

## What you need before you start

| Thing | Why | Cost |
|---|---|---|
| GitHub account | Streamlit Cloud deploys from a repository | free |
| Streamlit Community Cloud account | hosting | free |
| Neon Postgres project | owner decisions must survive a restart | free |
| Groq API key *(optional)* | the AI Business Analyst's wording | free tier |

Without Groq the analyst still answers — in the engine's own wording. Without Neon the
application still runs, but a recorded decision is lost on the next restart.

## Steps

**1. Create the Neon database.** Sign up at neon.com, create a project, copy the pooled
connection string. It looks like `postgresql://user:pass@host/db?sslmode=require`.

**2. Get a Groq key** *(optional)*. console.groq.com -> API key. Note a model id.

**3. Push this repository to GitHub.** It must be one repository containing the application AND
the evidence export — the engine reconstructs every figure from those CSVs at startup.

```bash
git init && git add -A && git commit -m "Owner Analytics on Streamlit"
```

```bash
git remote add origin https://github.com/<you>/<repo>.git && git branch -M main && git push -u origin main
```

**4. Deploy.** share.streamlit.io -> **New app** -> pick the repository, branch `main`, main file
`streamlit_app.py`.

**5. Add the secrets.** In **Advanced settings -> Secrets**, paste:

```toml
DATABASE_URL = "postgresql://...your Neon string..."

AI_ANALYTICS_LLM_ENABLE = "true"
AI_ANALYTICS_LLM_MODE = "http"
AI_ANALYTICS_LLM_ADAPTER = "groq"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_API_KEY = "...your Groq key..."
GROQ_MODEL = "...your chosen model id..."
```

Streamlit exposes these to the process as environment variables. They stay server-side; nothing
in `owner_app/` renders them.

**6. Make the URL private.** In **Settings -> Sharing**, keep the app unlisted and share the link
with nobody else. There is no login screen: **the URL is the credential.**

Your URL will be `https://<app-name>.streamlit.app`.

## First load

The engine reconstructs its payloads from the evidence export before the first page draws. That
takes roughly a minute on Community Cloud hardware, and happens once: the service is held in
`st.cache_resource`, so every later page and every widget interaction reuses it. The bound export
is immutable, which is what makes holding it correct rather than merely fast.

## Environment variables

| Variable | Secret | Effect if unset |
|---|---|---|
| `DATABASE_URL` | **yes** | decisions fall back to a SQLite file, lost on restart |
| `GROQ_API_KEY` | **yes** | the analyst answers in the engine's own wording |
| `GROQ_MODEL` | **yes** | as above |
| `AI_ANALYTICS_LLM_ENABLE` / `_MODE` / `_ADAPTER` | no | as above |
| `GROQ_BASE_URL` | no | as above |
| `AI_ANALYTICS_BASE` | no | defaults to the package directory — leave it unset |

Never set `SUPABASE_SERVICE_ROLE_KEY`; the live connector refuses it, and the live source stays
quarantined for this deployment regardless.

## Data

The trusted CSV export is bundled in the repository and is what the application reads. The live
Supabase source is **not** enabled: it is opt-in behind the existing revalidation harness, and
nothing here turns it on. `AnalyticsService` still runs the quarantine gate at startup, so a
source that fails revalidation is refused exactly as it is today.

## Free-tier limitations

- **Community Cloud gives roughly 1 GB of memory.** The engine measured ~300 MB resident after
  warming, so it fits — with real but not generous headroom.
- **Apps sleep after about a week of inactivity** and wake on the next visit, paying the ~1 minute
  warm-up again.
- **Neon free** is 0.5 GB and suspends its compute after 5 minutes idle, waking on the next
  connection. Decisions are tiny, so size is not a constraint.
- **Groq free** has per-minute rate limits. Exceeding them makes the analyst answer in the
  engine's own wording, which is the designed behaviour and not an outage.
- **The URL is the credential.** Anyone who has it can read the business.

## Running it locally

```bash
streamlit run streamlit_app.py
```
