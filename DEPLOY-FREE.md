# Deploying for free

`render.yaml` is now set to Render's **free tier (no credit card)**. Here are the
free options, easiest first.

---

## Option 1 — Render, free tier (you're already set up here)

The Blueprint asked for a card only because it previously requested a paid
*persistent disk*. That's removed now.

1. Push the updated config:
   ```powershell
   cd "C:\Users\vijay\OneDrive - Essar\Desktop\Intellia Signals Engine\cority-esbd-agents"
   git add render.yaml && git commit -m "Use Render free tier" && git push
   ```
2. In Render, open your Blueprint and **re-sync** (or delete it and create a new
   one from the repo). It should now show **plan: free** and deploy with **no
   payment**.

**If the Blueprint still asks for a card,** skip the Blueprint and create the
service manually — this path never asks for payment:
> Render → **New +** → **Web Service** → connect the `cority-esbd-engine` repo →
> Language/Runtime: **Docker** → Instance Type: **Free** → **Create Web Service**.
(It auto-detects the `Dockerfile`; ignore `render.yaml` in this flow.)

**Free-tier limits to expect**
- **512 MB RAM** — fine for keyword searches (Agents 1 & 2). A heavy **Agent 3**
  run (real browser + many attachments) can hit out-of-memory and restart. If
  that happens, use Option 2 below.
- **Sleeps after ~15 min idle** — first visit then takes ~1 minute to wake.
- **No persistent storage** — the workbook/attachments reset when it sleeps or
  redeploys. So: run Agents 1 → 2 → 3 in one sitting and click **Download
  Workbook** right after.

---

## Option 2 — Hugging Face Spaces (free, much more RAM) ⭐ if Render is too tight

Free **Docker Spaces** give **2 vCPU / 16 GB RAM** — plenty for Chromium — and
need no credit card. Best free option if Agent 3 crashes on Render.

1. Create a free account at https://huggingface.co
2. **New → Space** → SDK: **Docker** → **Blank** → Visibility: **Private** → Create.
3. It opens a git repo. Add this metadata to the **top of its `README.md`**
   (Spaces require it; `app_port` must match the container's port, 5000):
   ```
   ---
   title: Cority ESBD Engine
   emoji: 🦺
   colorFrom: indigo
   colorTo: orange
   sdk: docker
   app_port: 5000
   pinned: false
   ---
   ```
4. Copy this project's files into that repo (`Dockerfile`, `backend/`,
   `frontend/`, `assets/`) and push. The same Dockerfile works unchanged.

> Tell me if you want this route and I'll generate the exact files + push
> commands for the Space.

---

## Option 3 — Run locally, share via Cloudflare Tunnel (free, full power)

No cloud limits at all — it runs on your PC (16 GB+ RAM, persistent files) and is
reachable on the internet while your machine is on.

1. Start the app: double-click `start.bat`.
2. Install cloudflared (one time): https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
3. In a terminal: `cloudflared tunnel --url http://localhost:5000`
   → it prints a public `https://<random>.trycloudflare.com` URL you can share.

Best if you want zero cost **and** full reliability, and don't mind the app only
being online while your computer is.

---

### Quick recommendation
- Just you, light use → **Render free** (Option 1). Try it first.
- Agent 3 keeps crashing / heavier use → **Hugging Face Spaces** (Option 2).
- Want full power for $0 and your PC can stay on → **Cloudflare Tunnel** (Option 3).
