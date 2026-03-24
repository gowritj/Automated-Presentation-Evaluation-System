# Async Video Processing — Setup Guide

This document covers **exactly** what changed and how to run the new
async pipeline.  Nothing in the existing synchronous routes was touched —
`/api/upload-video` and `/api/upload-video-sse` still work identically.

---

## What was added

| File | What it does |
|------|--------------|
| `celery_worker.py` | Celery app + the `process_video_task` Celery task |
| `static/js/upload-async.js` | Frontend polling logic (replaces `upload.js` for async flow) |
| `requirements-async.txt` | Two new packages: `celery` + `redis` |
| `docker-compose.yml` | Spins up Redis + worker + Flask for local dev |
| `Dockerfile` | Container image used by docker-compose |

**In `app.py`** two new routes were appended (nothing existing was modified):

```
POST  /api/upload-video-async   ← non-blocking upload, returns job_id
GET   /api/job-status/<job_id>  ← frontend polls this every 5 seconds
```

---

## How it works

```
Browser                Flask                  Redis          Celery Worker
  │                      │                      │                  │
  │── POST /upload-async ─►│                      │                  │
  │                      │── upload to Cloudinary │                  │
  │                      │── save Video to DB     │                  │
  │                      │── task.delay() ────────►│                  │
  │◄── 202 { job_id } ───│                      │── enqueue ────────►│
  │                      │                      │                  │
  │ (poll every 5 s)     │                      │  CV + Whisper     │
  │── GET /job-status ──►│◄── PROGRESS 55% ─────┤  + Groq           │
  │◄── { percent: 55 } ──│                      │                  │
  │                      │                      │                  │
  │── GET /job-status ──►│◄── SUCCESS ──────────┤◄── done ─────────│
  │◄── { state: SUCCESS }│                      │                  │
  │                      │                      │                  │
  │── redirect /analysis │                      │                  │
```

---

## Installation

### 1. Add the new packages

```bash
pip install celery==5.4.0 redis==5.0.8
```

Or merge `requirements-async.txt` into `requirements.txt`.

### 2. Add `REDIS_URL` to `.env`

```env
# Local Redis (default if you run docker-compose)
REDIS_URL=redis://localhost:6379/0

# Or a managed Redis (Upstash, Redis Cloud, Railway, etc.)
REDIS_URL=rediss://:password@hostname:6380/0
```

### 3. Start Redis

**Option A — Docker (easiest)**
```bash
docker run -d -p 6379:6379 redis:7-alpine
```

**Option B — docker-compose (starts everything)**
```bash
docker compose up
```

**Option C — hosted Redis** — set `REDIS_URL` to your provider URL and skip this step.

### 4. Start the Celery worker

```bash
celery -A celery_worker.celery_app worker \
  --loglevel=info \
  --concurrency=2 \
  --queues=video_processing
```

`--concurrency=2` means 2 videos are processed simultaneously.  Each job
uses significant CPU/RAM (MediaPipe + Whisper + OpenCV), so don't raise
this above the number of CPU cores you have.

### 5. Start Flask

```bash
python app.py
# or: gunicorn app:app -w 4
```

### 6. Switch the upload page to the async script

In your upload HTML template, change:

```html
<!-- before -->
<script type="module" src="/static/js/upload.js"></script>

<!-- after -->
<script type="module" src="/static/js/upload-async.js"></script>
```

That's it.  The new JS file handles everything: posting to the async
endpoint, showing the same progress overlay, polling, and redirecting.

---

## Deployment (Railway / Render / Fly.io)

1. Add Redis as a plugin/add-on — copy the `REDIS_URL` into your env vars.
2. Deploy the web service as normal.
3. Add a **second service** (worker) with the start command:
   ```
   celery -A celery_worker.celery_app worker --loglevel=info --concurrency=2
   ```
4. Give the worker service the same env vars as the web service.

---

## API reference

### `POST /api/upload-video-async`

Same request body as `/api/upload-video`.  Returns immediately (< 2 s).

**Response 202**
```json
{
  "job_id":   "abc123-...",
  "video_id": 42,
  "message":  "Upload successful. Processing has started.",
  "poll_url": "/api/job-status/abc123-..."
}
```

### `GET /api/job-status/<job_id>`

**While running**
```json
{ "state": "PROGRESS", "percent": 55, "label": "Analysing speech…", "stage": "speech" }
```

**On success**
```json
{
  "state": "SUCCESS",
  "result": {
    "video_id": 42,
    "overall_score": 83.4,
    "posture_score": 78.0,
    "gesture_score": 65.0,
    "eye_contact_score": 91.0,
    "speech_rate_score": 88.0,
    "filler_score": 72.0,
    "vocabulary_score": 80.0,
    "confidence_score": 85.0,
    "topic_relevance_score": 79.0,
    "content_structure_score": 82.0
  }
}
```

**On failure**
```json
{ "state": "FAILURE", "error": "…" }
```

**Pending (worker not started yet)**
```json
{ "state": "PENDING", "percent": 0, "label": "Waiting in queue…" }
```

---

## Stage → progress mapping

| Stage code | Percent | What's happening |
|------------|---------|-----------------|
| `pending`  | 0       | Job queued, worker not started yet |
| `cv`       | 10      | Downloading video + MediaPipe posture/gesture/eye-contact |
| `speech`   | 55      | Whisper transcription + speech metrics |
| `groq`     | 70      | Groq LLM content analysis |
| `scoring`  | 85      | Computing weighted overall score |
| `db`       | 93      | Writing Analysis row to database |
| `done`     | 100     | Complete — frontend redirects |

---

## FAQ

**Q: The old SSE route (`/api/upload-video-sse`) still blocks a thread — should I remove it?**  
A: Keep it for now as a fallback.  Once you've confirmed the async flow
works in production you can remove it, but having both doesn't hurt.

**Q: What happens if the worker crashes mid-job?**  
Celery is configured with `task_acks_late=True` and
`task_reject_on_worker_lost=True`.  If the worker dies the task goes back
to the queue and will be retried once by another worker.  The Video row in
the DB will be cleaned up if both attempts fail.

**Q: What if the user closes the browser tab?**  
The job keeps running on the worker.  When the user comes back (or you
send them a notification), you can resume polling with the saved `job_id`.
Results live in Redis for 24 hours (`result_expires=86400`).

**Q: Do I need to change the database schema?**  
No.  The Analysis model is unchanged.  The Celery task writes to the same
table using the same SQLAlchemy models.
