# Deploying to Render

This app runs on Render as a **Docker web service** with a **persistent disk**.
Everything is preconfigured — you mainly push the code to GitHub and click through
Render's Blueprint flow.

---

## Step 0 — One-time accounts
- A free **GitHub** account: https://github.com
- A free **Render** account (sign in with GitHub): https://render.com

---

## Step 1 — Put the code on GitHub

I've already initialized a git repo and committed everything in this folder.
Create an empty repo on GitHub (no README/license), then from a terminal in
`cority-esbd-agents`:

```bash
git remote add origin https://github.com/<your-username>/cority-esbd-engine.git
git branch -M main
git push -u origin main
```

> If `git push` asks you to log in, use your GitHub username and a **Personal
> Access Token** (GitHub → Settings → Developer settings → Tokens) as the password.

---

## Step 2 — Deploy on Render (Blueprint)

1. Render Dashboard → **New +** → **Blueprint**.
2. Connect your GitHub and pick the **cority-esbd-engine** repo.
3. Render detects [`render.yaml`](render.yaml) and shows a service named
   **cority-esbd-engine** (Docker, Starter plan, 1 GB disk). Click **Apply**.
4. The first build takes ~5–8 minutes (it installs Chromium). When it's done you
   get a URL like `https://cority-esbd-engine.onrender.com`.

Open that URL — the Cority UI loads and the agents work exactly as they do
locally.

---

## Plan & cost notes

| Plan | Cost | Disk? | Good for |
|---|---|---|---|
| **Free** | $0 | ❌ (must remove `disk:` from `render.yaml`) | Trying it out. Sleeps after 15 min idle (≈1 min cold start); outputs reset on restart. |
| **Starter** ⭐ | ~$7/mo | ✅ | Recommended default. Always on, workbook/attachments persist. |
| **Standard** | ~$25/mo | ✅ | If agent runs crash with out-of-memory (Chromium is RAM‑hungry) — 2 GB. |

**To use the Free tier:** in `render.yaml` delete the whole `disk:` block and
change `plan: starter` to `plan: free`, then push.

---

## How it's wired (for reference)
- [`Dockerfile`](Dockerfile) — Python 3.12 + Chromium (via `playwright install
  --with-deps`); served by gunicorn (1 worker so the live‑job registry is shared).
- [`render.yaml`](render.yaml) — the Blueprint: Docker service + 1 GB disk mounted
  at `/app/data` (where the workbook, CSVs and attachments are stored).
- The app listens on Render's `$PORT` automatically.

## Updating later
Just commit and push — Render auto-deploys every push to `main`:
```bash
git add -A && git commit -m "tweak" && git push
```

## Troubleshooting
- **Build fails on Chromium / browser launch** → ensure you deployed via Docker
  (the Blueprint does this; don't pick the "Python" native runtime).
- **Agent run dies / 502 during Agent 3** → likely out-of-memory; bump the plan to
  Standard (2 GB) in the Render dashboard (Settings → Instance Type).
- **Outputs disappeared after a redeploy on Free** → expected; Free has no disk.
  Move to Starter for persistence.
- **Government site rate-limits the cloud IP** → run from the office instead
  (the local `start.bat`), or contact me to add retry/backoff.
