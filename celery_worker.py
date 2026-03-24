"""
celery_worker.py
────────────────
Celery application + the single async task that runs the full ML pipeline.

Start the worker with:
    celery -A celery_worker.celery_app worker --loglevel=info --concurrency=2

The --concurrency=2 flag limits how many videos are processed at once.
Each video job can take 2-4 minutes and is CPU/memory heavy, so keep
this low unless you have a beefy machine.
"""

import os
import json
import tempfile
import ssl
import cloudinary
import cloudinary.uploader
import requests
import whisper
from celery import Celery
from dotenv import load_dotenv
from moviepy import VideoFileClip

# ── Import all CV + scoring helpers from app.py ──────────────────────────────
# We import from app.py directly so there is one source of truth for every
# scoring algorithm.  Flask's application context is NOT needed for any of
# these functions — they are pure Python / numpy / mediapipe code.
from app import (
    app as flask_app,          # needed only to push an app context for SQLAlchemy
    db,
    Video,
    Analysis,
    calculate_posture,
    calculate_gesture,
    calculate_eye_contact,
    evaluate_text,
    score_speech_rate,
    score_filler_words,
    score_vocabulary,
    score_confidence_language,
    analyse_content_with_groq,
    build_feedback,
    process_video_from_cloudinary,
)

load_dotenv()

# ─────────────────────────────────────────
# CELERY CONFIG
# ─────────────────────────────────────────

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
if not REDIS_URL:
    raise ValueError("REDIS_URL is not set!")
celery_app = Celery(
    "presentation_eval",
    broker=REDIS_URL,
    backend=REDIS_URL,
)


celery_app.conf.broker_use_ssl = {"ssl_cert_reqs": ssl.CERT_NONE}
celery_app.conf.redis_backend_use_ssl = {"ssl_cert_reqs": ssl.CERT_NONE}
celery_app.conf.update(
    # Serialisation
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Results live for 24 hours — long enough for any reasonable frontend poll
    result_expires=86400,
    # Retry a failed task once after 60 seconds before giving up
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Route all tasks to the default queue
    task_default_queue="video_processing",
    # Timezone
    timezone="UTC",
    enable_utc=True,
)


# ─────────────────────────────────────────
# THE ASYNC TASK
# ─────────────────────────────────────────

@celery_app.task(
    bind=True,
    max_retries=1,
    soft_time_limit=600,   # 10 min soft limit  → raises SoftTimeLimitExceeded
    time_limit=660,        # 11 min hard limit   → SIGKILL
    name="process_video",
)
def process_video_task(self, video_id: int, cloudinary_url: str, video_title: str):
    """
    Runs the full ML pipeline for a single uploaded video.

    Parameters
    ----------
    video_id       : int   — DB primary key of the already-saved Video row
    cloudinary_url : str   — secure Cloudinary URL to download the video from
    video_title    : str   — used by Groq content analysis as the topic

    The task updates its own state at each stage so the frontend can show a
    live progress bar.  Final state is either SUCCESS (result = analysis dict)
    or FAILURE (result = {"error": "..."}).
    """

    def _update(stage: str, percent: int, label: str):
        """Push a progress update visible via AsyncResult.info."""
        self.update_state(
            state="PROGRESS",
            meta={"stage": stage, "percent": percent, "label": label},
        )

    try:
        # ── Stage 1: Download + run CV pipelines ─────────────────────────────
        _update("cv", 10, "Downloading video…")
        (
            text,
            duration,
            silent,
            posture_score,
            gesture_score,
            eye_contact_score,
        ) = process_video_from_cloudinary(cloudinary_url)

        # ── Stage 2: Speech analysis ──────────────────────────────────────────
        _update("speech", 55, "Analysing speech…")
        if silent or len(text.split()) < 10:
            speech_rate = filler_words = 0
            vocabulary_score = confidence_score = 0.0
            topic_relevance_score = content_structure_score = 0.0
            topic_relevance_reason = content_structure_reason = "No speech detected."
        else:
            speech_rate, filler_words = evaluate_text(text, duration)
            vocabulary_score = score_vocabulary(text)
            confidence_score = score_confidence_language(text, duration)

            # ── Stage 3: Groq content analysis ───────────────────────────────
            _update("groq", 70, "Scoring content with AI…")
            content_result = analyse_content_with_groq(text, video_title)
            topic_relevance_score = content_result["topic_relevance_score"]
            content_structure_score = content_result["content_structure_score"]
            topic_relevance_reason = content_result["topic_relevance_reason"]
            content_structure_reason = content_result["content_structure_reason"]

        # ── Stage 4: Compute overall score ───────────────────────────────────
        _update("scoring", 85, "Computing overall score…")
        speech_rate_score = score_speech_rate(speech_rate)
        filler_score = score_filler_words(filler_words, duration)

        overall_score = round(
            (
                eye_contact_score * 0.20
                + posture_score * 0.15
                + topic_relevance_score * 0.15
                + speech_rate_score * 0.10
                + filler_score * 0.10
                + vocabulary_score * 0.10
                + confidence_score * 0.10
                + content_structure_score * 0.05
                + gesture_score * 0.05
            ),
            2,
        )

        # ── Stage 5: Persist to DB ────────────────────────────────────────────
        _update("db", 93, "Saving results…")
        with flask_app.app_context():
            analysis = Analysis(
                video_id=video_id,
                speech_rate=float(round(speech_rate, 2)),
                filler_words=int(filler_words),
                posture_score=float(posture_score),
                eye_contact_score=float(eye_contact_score),
                gesture_score=float(gesture_score),
                overall_score=float(overall_score),
                duration=float(round(duration, 2)),
                vocabulary_score=float(vocabulary_score),
                confidence_score=float(confidence_score),
                topic_relevance_score=float(topic_relevance_score),
                content_structure_score=float(content_structure_score),
                topic_relevance_reason=topic_relevance_reason,
                content_structure_reason=content_structure_reason,
            )
            db.session.add(analysis)
            db.session.commit()

        result = {
            "video_id": video_id,
            "overall_score": overall_score,
            "posture_score": posture_score,
            "gesture_score": gesture_score,
            "eye_contact_score": eye_contact_score,
            "speech_rate_score": speech_rate_score,
            "filler_score": filler_score,
            "vocabulary_score": vocabulary_score,
            "confidence_score": confidence_score,
            "topic_relevance_score": topic_relevance_score,
            "content_structure_score": content_structure_score,
        }

        _update("done", 100, "Analysis complete!")
        return result

    except Exception as exc:
        # On failure, mark the Video row so the frontend knows to clean up
        with flask_app.app_context():
            video = db.session.get(Video, video_id)
            if video:
                # Delete the orphaned video record — Cloudinary asset was
                # already uploaded, caller can decide whether to purge it
                db.session.delete(video)
                db.session.commit()

        # Celery will store this exception in the result backend
        raise exc
