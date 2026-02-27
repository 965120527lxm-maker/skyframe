# SkyFrame v2 — AI Drone Video Enhancement

Upload drone footage → AI upscale via Replicate → download enhanced video.

## Architecture (recommended: same-origin)

```

┌───────────────┐     ┌─────────────┐     ┌─────────────┐     ┌───────────┐
│ Browser       │────▶│  FastAPI     │────▶│  Replicate  │────▶│ AI Model  │
│ (Frontend UI) │◀────│  Backend     │◀────│  API        │◀────│ (GPU)     │
└──────┬────────┘     └─────┬───────┘     └─────────────┘     └───────────┘
│                    │
│              ┌─────▼──────┐
│              │  SQLite DB │  uploads + jobs tables
│              └─────┬──────┘
│                    │
│              ┌─────▼──────┐
└─────────────▶│  Storage   │  original + enhanced videos (local disk)
└────────────┘

```

**Why same-origin?**
- Frontend calls API via relative paths (`/api/...`) — no hard-coded host/port.
- Easier to share publicly (only expose one port).

---

## Quick Start (recommended: one port)

### 1) Setup
```bash
cd backend
conda env create -f ../environment.yml
conda activate skyframe
````

### 2) Set your Replicate token

```bash
export REPLICATE_API_TOKEN=r8_your_token_here
# Get one at: https://replicate.com/account/api-tokens
```

### 3) Start backend (serves both API + frontend)

Option A (recommended in dev):

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 4) Open the app

* [http://localhost:8000](http://localhost:8000)

---

## Share a temporary public URL (TryCloudflare)

Once your server is running on localhost:

```bash
cloudflared tunnel --url http://localhost:8000
```

It will print a random `https://xxxx.trycloudflare.com` URL you can share.

> Note: Quick tunnels may not work if `~/.cloudflared/config.yaml` exists. Temporarily rename it if needed.

## API Endpoints

### Uploads

| Method | Path                       | Description         |
| ------ | -------------------------- | ------------------- |
| POST   | /api/uploads/init          | Reserve upload slot |
| PUT    | /api/uploads/{id}/file     | Upload file         |
| POST   | /api/uploads/{id}/complete | Mark done           |
| GET    | /api/uploads/{id}          | File details        |
| GET    | /api/uploads/{id}/download | Download original   |
| GET    | /api/uploads               | List uploads        |

### AI Jobs

| Method | Path                    | Description             |
| ------ | ----------------------- | ----------------------- |
| POST   | /api/jobs/create        | Start AI enhancement    |
| GET    | /api/jobs/{id}          | Job status + progress   |
| GET    | /api/jobs/{id}/download | Download enhanced video |
| GET    | /api/uploads/{id}/jobs  | List jobs for upload    |
| GET    | /api/models             | Available AI models     |

---

## AI Models

| Key               | Model                      | Notes                     |
| ----------------- | -------------------------- | ------------------------- |
| `upscale`         | lucataco/real-esrgan-video | Open-source, good default |
| `upscale_premium` | topazlabs/video-upscale    | Higher quality, paid      |

Switch models via the API:

```json
POST /api/jobs/create
{ "uploadId": "upl_xxx", "model": "upscale_premium" }
```

---

## How the Enhancement Flow Works

1. User clicks "AI Enhance" → frontend calls `POST /api/jobs/create`
2. Backend creates a job record (status: `pending`)
3. Background task submits video to Replicate API
4. Frontend polls `GET /api/jobs/{id}` every 3 seconds
5. When Replicate finishes, backend downloads the enhanced video
6. Job status → `completed`, download button appears
7. User downloads enhanced video via `GET /api/jobs/{id}/download`

---

## Cost

Replicate billing depends on model + runtime/hardware. Check each model page for estimates.

* `lucataco/real-esrgan-video`: model page shows an approximate cost per run (varies by input).
* `topazlabs/video-upscale`: model page provides a rough cost guide by output duration/resolution.

---

## Next Steps

* [ ] Add S3 storage (replace local disk)
* [ ] Webhook support (instead of polling)
* [ ] User auth
* [ ] Multiple enhancement options (stabilization, color grading)
* [ ] Side-by-side before/after preview

# skyframe
