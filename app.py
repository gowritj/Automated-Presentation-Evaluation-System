import firebase_admin
from firebase_admin import credentials, auth as firebase_auth
from flask import Flask, request, jsonify, render_template, Response, stream_with_context
import queue, threading, json as _json
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from dotenv import load_dotenv
import os
import re
import tempfile
import cloudinary
import cloudinary.uploader
import whisper
from moviepy import VideoFileClip
import requests
import cv2
import mediapipe as mp
import numpy as np
from groq import Groq
import json
load_dotenv()
# ─────────────────────────────────────────
# FILE VALIDATION
# ─────────────────────────────────────────

ALLOWED_EXTENSIONS = {"mp4", "mov", "avi", "webm"}
MAX_FILE_SIZE_MB = 500

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
# ─────────────────────────────────────────
# CLOUDINARY CONFIG
# ─────────────────────────────────────────
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

app = Flask(__name__)
CORS(app)

# ─────────────────────────────────────────
# DATABASE CONFIG
# ─────────────────────────────────────────
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "connect_args": {
        "sslmode": "require"
    }
}

db = SQLAlchemy(app)

# Load Whisper once at startup — using tiny model for speed.
# Upgrade to "base" or "small" for better accuracy at the cost of speed.
model = whisper.load_model("tiny")

# Groq client for content analysis — free LLM API
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Firebase Admin SDK — for server-side token verification
cred = credentials.Certificate(os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH"))
firebase_admin.initialize_app(cred)


# ─────────────────────────────────────────
# DATABASE MODELS
# ─────────────────────────────────────────

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    firebase_uid = db.Column(db.String(200), unique=True, nullable=False)
    email = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    name = db.Column(db.String(200))
    tags = db.relationship("Tag", backref="user", lazy=True)
    videos = db.relationship("Video", backref="user", lazy=True)


class Tag(db.Model):
    __tablename__ = "tags"

    id = db.Column(db.Integer, primary_key=True)
    tag_name = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    videos = db.relationship("Video", backref="tag", lazy=True)


class Video(db.Model):
    __tablename__ = "videos"

    id = db.Column(db.Integer, primary_key=True)
    video_title = db.Column(db.String(200))
    cloudinary_url = db.Column(db.Text, nullable=False)
    cloudinary_public_id = db.Column(db.String(200))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    tag_id = db.Column(db.Integer, db.ForeignKey("tags.id"), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    analysis = db.relationship("Analysis", backref="video", uselist=False)


class Analysis(db.Model):
    __tablename__ = "analysis"

    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey("videos.id"), nullable=False)
    speech_rate = db.Column(db.Float)
    filler_words = db.Column(db.Integer)
    posture_score = db.Column(db.Float)
    eye_contact_score = db.Column(db.Float)
    gesture_score = db.Column(db.Float)
    overall_score = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    duration = db.Column(db.Float)
    vocabulary_score = db.Column(db.Float)       
    confidence_score = db.Column(db.Float)           
    topic_relevance_score = db.Column(db.Float) 
    content_structure_score = db.Column(db.Float)    
    topic_relevance_reason = db.Column(db.Text)      
    content_structure_reason = db.Column(db.Text)


# ─────────────────────────────────────────
# VIDEO PROCESSING — MAIN PIPELINE
# ─────────────────────────────────────────

def process_video_from_cloudinary(video_url):
    """
    Downloads the video from Cloudinary to a temp file,
    runs all CV pipelines, extracts audio, and returns
    all raw scores + transcript for further processing.
    """

    # Download video from Cloudinary to a local temp file
    response = requests.get(video_url, stream=True)
    temp_video = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    for chunk in response.iter_content(chunk_size=8192):
        temp_video.write(chunk)
    temp_video.close()  # Must close before OpenCV/ffmpeg reads it

    video_path = temp_video.name
    try:
        # Run all three CV pipelines on the same video file
        posture_score = calculate_posture(video_path)
        gesture_score = calculate_gesture(video_path)
        eye_contact_score = calculate_eye_contact(video_path)

        # Extract audio for Whisper transcription
        video = VideoFileClip(video_path)
        temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        audio_path = temp_audio.name
        temp_audio.close()

        # Handle videos with no audio track at all
        if video.audio is None:
            duration = video.duration
            video.close()
            return "", duration, True, posture_score, gesture_score, eye_contact_score

        video.audio.write_audiofile(audio_path)

        # Check if audio is essentially silent (volume too low for Whisper)
        audio = video.audio
        volume = audio.max_volume()
        silent = volume < 0.01

        duration = video.duration
        video.close()

        # Transcribe audio using Whisper
        result = model.transcribe(audio_path)
        text = result["text"]

        os.remove(audio_path)

        return text, duration, silent, posture_score, gesture_score, eye_contact_score

    finally:
        # Always clean up temp video file even if something crashes
        if os.path.exists(video_path):
            os.remove(video_path)


# ─────────────────────────────────────────
# SPEECH ANALYSIS
# ─────────────────────────────────────────

def evaluate_text(text, duration):
    """
    Computes speech rate (WPM) and counts filler words
    from the Whisper transcript.
    """
    words = text.split()
    word_count = len(words)
    speech_rate = word_count / (duration / 60)

    filler_list = ["um", "uh", "like", "actually", "basically"]

    # Use word boundary regex to avoid false matches
    # e.g. "like" should not match inside "likewise" or "unlikely"
    filler_words = 0
    for word in filler_list:
        filler_words += len(re.findall(rf'\b{word}\b', text.lower()))

    return speech_rate, filler_words


def score_speech_rate(wpm):
    """
    Converts WPM into a 0-100 score using a smooth linear curve.
    Ideal range is 120-150 WPM.
    Below 120: score drops linearly to 0 at 60 WPM.
    Above 150: score drops linearly to 0 at 220 WPM.
    Above 300: returns 0 — likely a Whisper hallucination on noisy audio.
    """
    if wpm <= 0 or wpm > 300:
        return 0.0
    if 120 <= wpm <= 150:
        return 100.0
    if wpm < 120:
        # Too slow — linear drop from 100 at 120 WPM to 0 at 60 WPM
        return max(0.0, round((wpm - 60) / (120 - 60) * 100, 2))
    # Too fast — linear drop from 100 at 150 WPM to 0 at 220 WPM
    return max(0.0, round((220 - wpm) / (220 - 150) * 100, 2))


def score_filler_words(filler_count, duration_seconds):
    """
    Converts filler word count into a 0-100 score.
    Normalised per minute so short and long videos are treated fairly.
    < 1 per minute  → 100 (excellent)
    < 3 per minute  → 80  (good)
    < 6 per minute  → 60  (acceptable)
    < 10 per minute → 40  (needs work)
    10+ per minute  → 20  (poor)
    """
    duration_minutes = duration_seconds / 60 if duration_seconds > 0 else 1
    fillers_per_minute = filler_count / duration_minutes

    if fillers_per_minute < 1:
        return 100.0
    elif fillers_per_minute < 3:
        return 80.0
    elif fillers_per_minute < 6:
        return 60.0
    elif fillers_per_minute < 10:
        return 40.0
    else:
        return 20.0

def score_vocabulary(text):
    """
    Measures vocabulary richness — unique words / total words.
    Ideal for presentations is 40-60% unique words.
    Below 30% is repetitive, above 50% is varied.
    """
    words = re.findall(r'\b[a-z]+\b', text.lower())
    if len(words) == 0:
        return 0.0
    unique_ratio = len(set(words)) / len(words)
    # Linear scale: 0.2 ratio = 0 score, 0.5 ratio = 100 score
    score = max(0.0, min(100.0, (unique_ratio - 0.2) / (0.5 - 0.2) * 100))
    return round(score, 2)


def score_confidence_language(text, duration_seconds):
    """
    Detects weak/hedging language that signals low confidence.
    Normalised per minute so short and long videos are treated fairly.
    """
    weak_phrases = [
        "i think", "i guess", "i'm not sure", "i am not sure",
        "maybe", "perhaps", "kind of", "sort of", "i don't know",
        "i do not know", "a little bit", "i feel like",
        "probably", "might be", "not really sure"
    ]
    text_lower = text.lower()
    count = sum(text_lower.count(phrase) for phrase in weak_phrases)
    duration_minutes = duration_seconds / 60 if duration_seconds > 0 else 1
    per_minute = count / duration_minutes

    if per_minute < 1:
        return 100.0
    elif per_minute < 2:
        return 80.0
    elif per_minute < 4:
        return 60.0
    elif per_minute < 7:
        return 40.0
    else:
        return 20.0


def analyse_content_with_groq(transcript, topic):
    """
    Sends transcript and topic to Groq for content analysis.
    Returns topic relevance score, structure score, and one-line reasons.
    Single API call returns both scores to save on rate limits.
    Falls back to 0 with error message if API call fails.
    """
    prompt = f"""You are an expert presentation coach. Analyse this speech transcript and return a JSON object only — no explanation, no markdown, just raw JSON.

Topic the speaker was supposed to present on: "{topic}"

Transcript:
{transcript}

Return exactly this JSON structure:
{{
  "topic_relevance_score": <0-100 integer>,
  "topic_relevance_reason": "<one sentence explaining the score>",
  "content_structure_score": <0-100 integer>,
  "content_structure_reason": "<one sentence explaining the score>"
}}

Scoring guide:
- topic_relevance_score: How well the speech covers the given topic. 90-100 = excellent coverage, 70-89 = good but missing some points, 50-69 = partial coverage, below 50 = mostly off-topic.
- content_structure_score: Does the speech have a clear intro, body, and conclusion? 90-100 = very clear structure, 70-89 = mostly structured, 50-69 = some structure but disorganised, below 50 = no clear structure."""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.1
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences if model wraps response in them
        raw = re.sub(r'```json|```', '', raw).strip()
        result = json.loads(raw)
        return {
            "topic_relevance_score": float(result.get("topic_relevance_score", 0)),
            "topic_relevance_reason": result.get("topic_relevance_reason", ""),
            "content_structure_score": float(result.get("content_structure_score", 0)),
            "content_structure_reason": result.get("content_structure_reason", "")
        }
    except Exception as e:
        print("Groq API error:", e)
        # Return a clear error payload so the caller knows analysis failed
        return {
            "topic_relevance_score": 0.0,
            "topic_relevance_reason": f"Analysis unavailable: {str(e)[:80]}",
            "content_structure_score": 0.0,
            "content_structure_reason": f"Analysis unavailable: {str(e)[:80]}"
        }

# ─────────────────────────────────────────
# POSTURE ANALYSIS
# ─────────────────────────────────────────

def calculate_posture(video_path):
    """
    Analyses posture from video using MediaPipe Pose.
    Designed for seated/half-body webcam recordings —
    does NOT use hip landmarks which are often out of frame.

    Scoring breakdown per frame (max 100):
      1. Shoulder alignment  — 30pts
      2. Head alignment      — 20pts
      3. Ear-shoulder angle  — 30pts (replaces hip-based spine angle)
      4. Forward head        — 10pts (replaces z-axis lean)
      5. Stability           — 10pts

    Samples every 10th frame for performance.
    Skips frames where key landmarks are low confidence (<0.5).
    Applies a slouch penalty based on ratio of bad posture frames.
    """
    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose()
    cap = cv2.VideoCapture(video_path)

    posture_scores = []
    slouch_frames = 0
    total_frames = 0
    sampled_frames = 0  # only counts frames where landmarks were confidently detected
    prev_shoulder_y = None

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        total_frames += 1

        # Sample every 10th frame for performance
        if total_frames % 10 != 0:
            continue

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(rgb)

        if results.pose_landmarks:
            lm = results.pose_landmarks.landmark

            left_shoulder  = lm[11]
            right_shoulder = lm[12]
            left_ear       = lm[7]
            right_ear      = lm[8]
            nose           = lm[0]

            # Skip frame if any key landmark is low confidence
            # Prevents garbage scores when person moves out of frame
            if (left_shoulder.visibility < 0.5 or right_shoulder.visibility < 0.5 or
                    left_ear.visibility < 0.5 or right_ear.visibility < 0.5):
                continue

            sampled_frames += 1
            score = 0

            # ─── 1. Shoulder alignment (30%) ───────────────────────
            # Checks if shoulders are level — tilting sideways loses points
            shoulder_diff = abs(left_shoulder.y - right_shoulder.y)
            if shoulder_diff < 0.04:
                score += 30
            elif shoulder_diff < 0.08:
                score += 15

            # ─── 2. Head alignment (20%) ────────────────────────────
            # Checks if head is centered over shoulders horizontally
            mid_x = (left_shoulder.x + right_shoulder.x) / 2
            head_offset = abs(nose.x - mid_x)
            if head_offset < 0.04:
                score += 20
            elif head_offset < 0.08:
                score += 10

            # ─── 3. Ear-shoulder angle / slouch detection (30%) ─────
            # Replaces hip-based spine angle for seated webcam use.
            # The vector from shoulder midpoint to ear midpoint should
            # point straight up when sitting upright. If slouching forward,
            # ears drop toward shoulders and the angle increases.
            shoulder_mid = np.array([
                (left_shoulder.x + right_shoulder.x) / 2,
                (left_shoulder.y + right_shoulder.y) / 2
            ])
            ear_mid = np.array([
                (left_ear.x + right_ear.x) / 2,
                (left_ear.y + right_ear.y) / 2
            ])

            neck_vector = ear_mid - shoulder_mid
            vertical_vector = np.array([0, -1])  # upward in image coords (Y increases downward)

            cos_angle = np.dot(neck_vector, vertical_vector) / (
                np.linalg.norm(neck_vector) * np.linalg.norm(vertical_vector) + 1e-6
            )
            cos_angle = np.clip(cos_angle, -1.0, 1.0)  # guard against float precision errors
            angle = np.degrees(np.arccos(cos_angle))

            if angle < 15:
                score += 30
            elif angle < 25:
                score += 15
            else:
                slouch_frames += 1  # counts toward slouch penalty

            # ─── 4. Forward head posture (10%) ──────────────────────
            # Replaces z-axis lean (unreliable on webcams).
            # Nose Y should be well above shoulder Y in image coords.
            # If nose.y approaches shoulder.y, the head is drooping forward.
            nose_to_shoulder_y = nose.y - (left_shoulder.y + right_shoulder.y) / 2
            if nose_to_shoulder_y < -0.15:
                score += 10  # head well above shoulders — good upright posture
            elif nose_to_shoulder_y < -0.08:
                score += 5   # slightly low but acceptable

            # ─── 5. Stability (10%) ─────────────────────────────────
            # Penalises excessive swaying or bouncing by tracking
            # how much shoulder height changes between sampled frames
            shoulder_mid_y = (left_shoulder.y + right_shoulder.y) / 2
            if prev_shoulder_y is not None:
                movement = abs(shoulder_mid_y - prev_shoulder_y)
                if movement < 0.01:
                    score += 10
                elif movement < 0.03:
                    score += 5

            prev_shoulder_y = shoulder_mid_y
            posture_scores.append(score)

    cap.release()

    if not posture_scores:
        return 0.0

    final_score = float(np.mean(posture_scores))

    # Apply slouch penalty based on proportion of bad posture frames
    slouch_ratio = (slouch_frames / sampled_frames) * 100 if sampled_frames else 0
    if slouch_ratio < 10:
        penalty = 0
    elif slouch_ratio < 30:
        penalty = 5
    elif slouch_ratio < 50:
        penalty = 10
    else:
        penalty = 20

    final_score = final_score - penalty
    final_score = max(0, min(100, final_score))  # clamp to 0-100

    return round(final_score, 2)


# ─────────────────────────────────────────
# GESTURE ANALYSIS
# ─────────────────────────────────────────

def calculate_gesture(video_path):
    """
    Analyses hand gestures using MediaPipe Hands.
    Tracks both hands, scoring on presence, movement,
    movement quality, frequency, and hand spread.

    Scoring breakdown (max 100):
      Presence score    — 30%  (how often hands are visible)
      Movement score    — 25%  (how often hands are actively moving)
      Movement quality  — 20%  (ideal movement range, not too static or shaky)
      Frequency score   — 15%  (how regularly gestures appear)
      Hand spread       — 10%  (expressive open gestures vs closed hands)

    Uses average of all 21 landmarks per hand instead of just the wrist,
    for more accurate movement tracking.
    Samples every 10th frame for performance.
    """
    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(max_num_hands=2)
    cap = cv2.VideoCapture(video_path)

    total_frames = 0
    gesture_frames = 0
    movement_values = []
    active_frames = 0
    spread_values = []
    prev_positions = []

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        total_frames += 1

        # Sample every 10th frame for performance
        if total_frames % 10 != 0:
            continue

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb)
        current_positions = []

        if results.multi_hand_landmarks:
            gesture_frames += 1

            for hand in results.multi_hand_landmarks:
                # Use average of all 21 landmarks instead of just wrist (landmark[0])
                # Gives a more accurate representation of overall hand position
                xs = [lm.x for lm in hand.landmark]
                ys = [lm.y for lm in hand.landmark]
                current_positions.append(np.array([np.mean(xs), np.mean(ys)]))

            # Track movement between frames
            if prev_positions and current_positions:
                for i in range(min(len(prev_positions), len(current_positions))):
                    movement = np.linalg.norm(current_positions[i] - prev_positions[i])
                    movement_values.append(movement)
                    if movement > 0.02:
                        active_frames += 1

            # Track spread between both hands when both are visible
            if len(current_positions) == 2:
                spread = np.linalg.norm(current_positions[0] - current_positions[1])
                spread_values.append(spread)

        prev_positions = current_positions

    cap.release()

    if total_frames == 0:
        return 0.0

    # Use sampled frame count for accurate percentages
    sampled_frames = total_frames // 10 if total_frames else 1

    # Presence: what fraction of sampled frames had hands visible
    presence_score = (gesture_frames / sampled_frames) * 100

    # Movement: what fraction of sampled frames had active hand movement
    movement_score = (active_frames / sampled_frames) * 100 if movement_values else 0

    # Movement quality: ideal is smooth, deliberate movement (not static, not shaky)
    if movement_values:
        avg_movement = np.mean(movement_values)
        if 0.02 < avg_movement < 0.08:
            quality_score = 100  # ideal — smooth deliberate gestures
        elif avg_movement < 0.02:
            quality_score = 40   # too static — hands barely moving
        else:
            quality_score = 50   # too shaky — excessive nervous movement
    else:
        quality_score = 0

    # Frequency: how regularly gestures appear (target ~60% of frames)
    frequency_score = min(100, (gesture_frames / (sampled_frames * 0.6)) * 100)

    # Hand spread: wide open gestures are more expressive than closed hands
    if spread_values:
        avg_spread = np.mean(spread_values)
        if avg_spread > 0.2:
            spread_score = 100  # expressive wide gestures
        elif avg_spread > 0.1:
            spread_score = 60   # moderate spread
        else:
            spread_score = 30   # hands too close together
    else:
        spread_score = 20  # no two-hand gestures detected

    final_score = (
        0.30 * presence_score +
        0.25 * movement_score +
        0.20 * quality_score +
        0.15 * frequency_score +
        0.10 * spread_score
    )

    return float(round(final_score, 2))


# ─────────────────────────────────────────
# EYE CONTACT ANALYSIS
# ─────────────────────────────────────────

def calculate_eye_contact(video_path):
    """
    Analyses eye contact using MediaPipe Face Mesh with iris tracking.
    refine_landmarks=True must be set to enable iris landmarks (468, 473).

    For each sampled frame, checks if both irises are horizontally
    centered within their eye socket. If the offset from center is
    small, the person is looking at the camera.

    Iris landmarks: 468 (left), 473 (right)
    Eye corner landmarks:
      Left eye:  33 (outer), 133 (inner)
      Right eye: 362 (outer), 263 (inner)

    Samples every 10th frame for performance.
    Skips frames where no face is detected.
    """
    mp_face_mesh = mp.solutions.face_mesh
    face_mesh = mp_face_mesh.FaceMesh(
        refine_landmarks=True,  # REQUIRED — enables iris landmarks 468 and 473
        max_num_faces=1         # only track the presenter, ignore background faces
    )

    cap = cv2.VideoCapture(video_path)
    total_frames = 0
    sampled_frames = 0
    eye_contact_frames = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        total_frames += 1

        # Sample every 10th frame for performance
        if total_frames % 10 != 0:
            continue

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb)

        if results.multi_face_landmarks:
            sampled_frames += 1
            landmarks = results.multi_face_landmarks[0].landmark

            # Iris centers (only available with refine_landmarks=True)
            left_iris  = landmarks[468]
            right_iris = landmarks[473]

            # Eye corner landmarks
            left_eye_outer  = landmarks[33]
            left_eye_inner  = landmarks[133]
            right_eye_outer = landmarks[362]
            right_eye_inner = landmarks[263]

            # Calculate how centered each iris is within its eye (0 = perfect center)
            left_eye_width  = abs(left_eye_outer.x - left_eye_inner.x)
            right_eye_width = abs(right_eye_outer.x - right_eye_inner.x)

            left_iris_offset = abs(
                left_iris.x - (left_eye_outer.x + left_eye_inner.x) / 2
            ) / (left_eye_width + 1e-6)

            right_iris_offset = abs(
                right_iris.x - (right_eye_outer.x + right_eye_inner.x) / 2
            ) / (right_eye_width + 1e-6)

            avg_offset = (left_iris_offset + right_iris_offset) / 2

            # Offset < 0.15 means iris is close enough to center = looking at camera
            if avg_offset < 0.15:
                eye_contact_frames += 1

    cap.release()

    if sampled_frames == 0:
        return 0.0

    score = (eye_contact_frames / sampled_frames) * 100
    return round(float(score), 2)


def build_feedback(speech_rate, filler_words, posture_score, eye_contact_score,
                   gesture_score, duration, vocabulary_score, confidence_score,
                   topic_relevance_score, content_structure_score,
                   topic_relevance_reason, content_structure_reason):
    """
    Generates human-readable feedback for each metric.
    Returns a dict with status (good/warning/bad) and msg for each metric.
    Used to explain to the student why their overall score is what it is.
    """
    feedback = {}

    # Speech rate feedback
    if speech_rate <= 0:
        feedback["speech_rate"] = {"status": "warning", "msg": "No speech detected."}
    elif speech_rate < 80:
        feedback["speech_rate"] = {"status": "bad", "msg": f"Too slow at {round(speech_rate)} WPM. Aim for 120–150 WPM."}
    elif speech_rate <= 150:
        feedback["speech_rate"] = {"status": "good", "msg": f"Great pace at {round(speech_rate)} WPM."}
    elif speech_rate <= 190:
        feedback["speech_rate"] = {"status": "warning", "msg": f"A bit fast at {round(speech_rate)} WPM. Try slowing down to 120–150 WPM."}
    else:
        feedback["speech_rate"] = {"status": "bad", "msg": f"Too fast at {round(speech_rate)} WPM. Slow down significantly."}

    # Filler words feedback
    fillers_per_min = round(filler_words / (duration / 60), 1) if duration > 0 else 0
    if fillers_per_min < 1:
        feedback["filler"] = {"status": "good", "msg": f"Excellent — only {filler_words} filler word(s) detected."}
    elif fillers_per_min < 3:
        feedback["filler"] = {"status": "warning", "msg": f"{filler_words} filler words ({fillers_per_min}/min). Try to reduce."}
    else:
        feedback["filler"] = {"status": "bad", "msg": f"Too many filler words — {filler_words} ({fillers_per_min}/min)."}

    # Posture feedback
    if posture_score >= 80:
        feedback["posture"] = {"status": "good", "msg": "Great posture throughout."}
    elif posture_score >= 55:
        feedback["posture"] = {"status": "warning", "msg": "Posture was okay but could be more upright."}
    else:
        feedback["posture"] = {"status": "bad", "msg": "Poor posture detected. Sit upright and keep shoulders level."}

    # Eye contact feedback
    if eye_contact_score >= 80:
        feedback["eye_contact"] = {"status": "good", "msg": "Strong eye contact with the camera."}
    elif eye_contact_score >= 55:
        feedback["eye_contact"] = {"status": "warning", "msg": "Eye contact was inconsistent. Look at the camera more."}
    else:
        feedback["eye_contact"] = {"status": "bad", "msg": "Poor eye contact. Avoid looking at notes or screen."}

    # Gesture feedback
    if gesture_score >= 60:
        feedback["gesture"] = {"status": "good", "msg": "Good use of hand gestures."}
    elif gesture_score >= 35:
        feedback["gesture"] = {"status": "warning", "msg": "Limited gestures. Try using your hands more naturally."}
    else:
        feedback["gesture"] = {"status": "bad", "msg": "Very few gestures detected. Engage your hands while speaking."}

    # Vocabulary feedback
    if vocabulary_score >= 70:
        feedback["vocabulary"] = {"status": "good", "msg": "Great vocabulary variety in your speech."}
    elif vocabulary_score >= 45:
        feedback["vocabulary"] = {"status": "warning", "msg": "Vocabulary was okay but try using more varied words."}
    else:
        feedback["vocabulary"] = {"status": "bad", "msg": "Speech was repetitive. Try to vary your word choices."}

    # Confidence language feedback
    if confidence_score >= 80:
        feedback["confidence"] = {"status": "good", "msg": "You spoke with confidence — minimal hedging language."}
    elif confidence_score >= 50:
        feedback["confidence"] = {"status": "warning", "msg": "Some hedging phrases detected. Avoid 'I think', 'maybe', 'kind of'."}
    else:
        feedback["confidence"] = {"status": "bad", "msg": "Too much uncertain language. Speak with more conviction."}

    # Topic relevance — use Groq's reason directly
    if topic_relevance_score >= 75:
        status = "good"
    elif topic_relevance_score >= 50:
        status = "warning"
    else:
        status = "bad"
    feedback["topic_relevance"] = {"status": status, "msg": topic_relevance_reason}

    # Content structure — use Groq's reason directly
    if content_structure_score >= 75:
        status = "good"
    elif content_structure_score >= 50:
        status = "warning"
    else:
        status = "bad"
    feedback["content_structure"] = {"status": status, "msg": content_structure_reason}

    return feedback

def verify_firebase_token(request):
    """
    Verifies the Firebase ID token sent in the Authorization header.
    Returns the decoded token (with uid, email etc.) if valid.
    Returns None if token is missing or invalid.
    
    Client must send: Authorization: Bearer <firebase_id_token>
    """
    auth_header = request.headers.get("Authorization")
    
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    
    id_token = auth_header.split("Bearer ")[1]
    
    try:
        decoded_token = firebase_auth.verify_id_token(id_token)
        return decoded_token
    except Exception as e:
        print("Firebase token verification failed:", e)
        return None


# ─────────────────────────────────────────
# ROUTES — VIDEO UPLOAD & ANALYSIS
# ─────────────────────────────────────────

@app.route("/api/upload-video", methods=["POST"])

def upload_video():
    decoded_token = verify_firebase_token(request)
    if not decoded_token:
        return jsonify({"error": "Unauthorized"}), 401
    # ✅ SIZE CHECK — MUST BE BEFORE reading file
    MAX_FILE_SIZE_MB = 500
    MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

    if request.content_length and request.content_length > MAX_FILE_SIZE_BYTES:
        return jsonify({
            "error": f"File too large. Max size is {MAX_FILE_SIZE_MB}MB."
        }), 400

    # ✅ Now check file exists
    if "video" not in request.files:
        return jsonify({"error": "No video file provided"}), 400

    video_file  = request.files["video"]
    # Validate file extension
    if not allowed_file(video_file.filename):
        return jsonify({
            "error": "Invalid file type. Only mp4, mov, avi, webm allowed."
        }), 400

    # Validate MIME type (extra safety)
    if not video_file.mimetype.startswith("video/"):
        return jsonify({
            "error": "Uploaded file is not a valid video."
        }), 400

    # Validate file size
    #video_file.seek(0, os.SEEK_END)
    #file_size_mb = video_file.tell() / (1024 * 1024)
    #video_file.seek(0)

    firebase_uid = request.form.get("firebase_uid")
    tag_name    = request.form.get("tag_name") or "General"
    video_title = request.form.get("video_title") or "Untitled"
    email       = request.form.get("email", "unknown@email.com")

    if not firebase_uid:
        return jsonify({"error": "firebase_uid missing"}), 400

    # Auto-create user record if this is their first upload
    user = User.query.filter_by(firebase_uid=firebase_uid).first()
    if not user:
        user = User(
            firebase_uid=firebase_uid,
            email=email,
            name=request.form.get("name", "User")
        )
        db.session.add(user)
        db.session.commit()

    # Find existing tag or create a new one
    tag = Tag.query.filter_by(user_id=user.id, tag_name=tag_name).first()
    if not tag:
        tag = Tag(tag_name=tag_name, user_id=user.id)
        db.session.add(tag)
        db.session.commit()

    # Upload video to Cloudinary
    try:
        result = cloudinary.uploader.upload_large(
            video_file.stream,
            resource_type="video"
        )
        cloudinary_url = result["secure_url"]
        public_id      = result["public_id"]
    except Exception as e:
        print("CLOUDINARY ERROR:", e)
        return jsonify({"error": str(e)}), 500

    # Save video record to DB before processing
    new_video = Video(
        video_title=video_title,
        cloudinary_url=cloudinary_url,
        cloudinary_public_id=public_id,
        user_id=user.id,
        tag_id=tag.id
    )
    db.session.add(new_video)
    db.session.commit()

    print("Processing video from Cloudinary...")

    try:
        # Run full pipeline — returns transcript + all CV scores
        text, duration, silent, posture_score, gesture_score, eye_contact_score = (
            process_video_from_cloudinary(cloudinary_url)
        )

        # Guard against silent or near-silent videos
        if silent or len(text.split()) < 10:
            speech_rate          = 0
            filler_words         = 0
            vocabulary_score     = 0.0
            confidence_score     = 0.0
            topic_relevance_score    = 0.0
            content_structure_score  = 0.0
            topic_relevance_reason   = "No speech detected."
            content_structure_reason = "No speech detected."
        else:
            speech_rate, filler_words = evaluate_text(text, duration)
            vocabulary_score     = score_vocabulary(text)
            confidence_score     = score_confidence_language(text, duration)
            content_result       = analyse_content_with_groq(text, video_title)
            topic_relevance_score    = content_result["topic_relevance_score"]
            content_structure_score  = content_result["content_structure_score"]
            topic_relevance_reason   = content_result["topic_relevance_reason"]
            content_structure_reason = content_result["content_structure_reason"]

        # Convert raw metrics to 0-100 scores
        speech_rate_score = score_speech_rate(speech_rate)
        filler_score      = score_filler_words(filler_words, duration)

        overall_score = round(
            (
                eye_contact_score       * 0.20 +
                posture_score           * 0.15 +
                topic_relevance_score   * 0.15 +
                speech_rate_score       * 0.10 +
                filler_score            * 0.10 +
                vocabulary_score        * 0.10 +
                confidence_score        * 0.10 +
                content_structure_score * 0.05 +
                gesture_score           * 0.05
            ),
        2
        )

        analysis = Analysis(
            video_id=new_video.id,
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
            content_structure_reason=content_structure_reason
        )
        db.session.add(analysis)
        db.session.commit()

    except Exception as e:
        print("PROCESSING ERROR — cleaning up:", e)
        # Delete DB record
        db.session.delete(new_video)
        db.session.commit()
        # Delete Cloudinary asset
        try:
            cloudinary.uploader.destroy(public_id, resource_type="video")
        except Exception as cloud_err:
            print("Cloudinary cleanup failed:", cloud_err)
        return jsonify({"error": "Analysis failed. Please try uploading again."}), 500

    return jsonify({
        "message": "Upload and analysis completed",
        "video_id": new_video.id,
        "cloudinary_url": cloudinary_url,
        "tag_name": tag.tag_name,
        "overall_score": overall_score
    })


# ─────────────────────────────────────────
# ROUTE — UPLOAD VIDEO (SSE progress)
# ─────────────────────────────────────────

@app.route("/api/upload-video-sse", methods=["POST"])
def upload_video_sse():
    """
    Identical pipeline to /api/upload-video but streams progress events so
    the browser can show per-stage feedback instead of a blank spinner.

    SSE event format (text/event-stream):
        data: {"stage": 1, "label": "Uploading video", "percent": 10}\n\n
        ...
        data: {"stage": 5, "label": "Done", "percent": 100, "video_id": 42}\n\n
        data: {"error": "..."}\n\n   ← on failure
    """

    # ── auth ────────────────────────────────────────────────────────────────
    decoded_token = verify_firebase_token(request)
    if not decoded_token:
        return jsonify({"error": "Unauthorized"}), 401

    # ── size guard ──────────────────────────────────────────────────────────
    MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024
    if request.content_length and request.content_length > MAX_FILE_SIZE_BYTES:
        return jsonify({"error": "File too large. Max size is 500 MB."}), 400

    if "video" not in request.files:
        return jsonify({"error": "No video file provided"}), 400

    video_file = request.files["video"]

    if not allowed_file(video_file.filename):
        return jsonify({"error": "Invalid file type. Only mp4, mov, avi, webm allowed."}), 400

    if not video_file.mimetype.startswith("video/"):
        return jsonify({"error": "Uploaded file is not a valid video."}), 400

    firebase_uid = request.form.get("firebase_uid")
    tag_name     = request.form.get("tag_name") or "General"
    video_title  = request.form.get("video_title") or "Untitled"
    email        = request.form.get("email", "unknown@email.com")

    if not firebase_uid:
        return jsonify({"error": "firebase_uid missing"}), 400

    # Read file bytes now — stream will be consumed inside the generator thread
    video_bytes    = video_file.read()
    video_filename = video_file.filename
    video_mimetype = video_file.mimetype

    # Queue used to pass results (or errors) from the worker thread back to
    # the SSE generator.
    result_q: queue.Queue = queue.Queue()

    def _worker():
        """Run the full pipeline in a background thread; push SSE messages."""

        def emit(stage, label, percent, **extra):
            payload = {"stage": stage, "label": label, "percent": percent, **extra}
            result_q.put(("event", payload))

        try:
            # ── DB: user / tag ──────────────────────────────────────────────
            with app.app_context():
                user = User.query.filter_by(firebase_uid=firebase_uid).first()
                if not user:
                    user = User(firebase_uid=firebase_uid, email=email, name="User")
                    db.session.add(user)
                    db.session.commit()

                tag = Tag.query.filter_by(user_id=user.id, tag_name=tag_name).first()
                if not tag:
                    tag = Tag(tag_name=tag_name, user_id=user.id)
                    db.session.add(tag)
                    db.session.commit()

                # ── Stage 1: upload to Cloudinary ───────────────────────────
                emit(1, "Uploading video", 10)

                import io
                stream = io.BytesIO(video_bytes)
                try:
                    result = cloudinary.uploader.upload_large(
                        stream, resource_type="video"
                    )
                    cloudinary_url = result["secure_url"]
                    public_id      = result["public_id"]
                except Exception as e:
                    result_q.put(("error", f"Cloudinary upload failed: {e}"))
                    return

                new_video = Video(
                    video_title=video_title,
                    cloudinary_url=cloudinary_url,
                    cloudinary_public_id=public_id,
                    user_id=user.id,
                    tag_id=tag.id,
                )
                db.session.add(new_video)
                db.session.commit()
                video_id = new_video.id

                emit(1, "Uploading video", 25)

                # ── Stage 2: CV pipeline ────────────────────────────────────
                emit(2, "Analysing posture and gestures", 35)

                try:
                    text, duration, silent, posture_score, gesture_score, eye_contact_score = (
                        process_video_from_cloudinary(cloudinary_url)
                    )
                except Exception as e:
                    db.session.delete(new_video)
                    db.session.commit()
                    try:
                        cloudinary.uploader.destroy(public_id, resource_type="video")
                    except Exception:
                        pass
                    result_q.put(("error", f"CV pipeline failed: {e}"))
                    return

                emit(2, "Analysing posture and gestures", 55)

                # ── Stage 3: Whisper transcription ──────────────────────────
                emit(3, "Transcribing speech", 65)

                # (transcription already done inside process_video_from_cloudinary)

                # ── Stage 4: Groq content analysis ──────────────────────────
                emit(4, "Analysing content", 75)

                if silent or len(text.split()) < 10:
                    speech_rate = filler_words = 0
                    vocabulary_score = confidence_score = 0.0
                    topic_relevance_score = content_structure_score = 0.0
                    topic_relevance_reason = content_structure_reason = "No speech detected."
                else:
                    speech_rate, filler_words = evaluate_text(text, duration)
                    vocabulary_score  = score_vocabulary(text)
                    confidence_score  = score_confidence_language(text, duration)
                    content_result    = analyse_content_with_groq(text, video_title)
                    topic_relevance_score    = content_result["topic_relevance_score"]
                    content_structure_score  = content_result["content_structure_score"]
                    topic_relevance_reason   = content_result["topic_relevance_reason"]
                    content_structure_reason = content_result["content_structure_reason"]

                emit(4, "Analysing content", 90)

                # ── finalise scores + DB ────────────────────────────────────
                speech_rate_score = score_speech_rate(speech_rate)
                filler_score      = score_filler_words(filler_words, duration)

                overall_score = round(
                    eye_contact_score       * 0.20 +
                    posture_score           * 0.15 +
                    topic_relevance_score   * 0.15 +
                    speech_rate_score       * 0.10 +
                    filler_score            * 0.10 +
                    vocabulary_score        * 0.10 +
                    confidence_score        * 0.10 +
                    content_structure_score * 0.05 +
                    gesture_score           * 0.05,
                    2,
                )

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

                emit(5, "Done", 100, video_id=video_id)
                result_q.put(("done", None))

        except Exception as e:
            result_q.put(("error", str(e)))

    # Start worker
    t = threading.Thread(target=_worker, daemon=True)
    t.start()

    def _sse_stream():
        while True:
            try:
                kind, payload = result_q.get(timeout=300)  # 5-min hard timeout
            except queue.Empty:
                yield "data: {\"error\": \"Processing timed out\"}\n\n"
                return

            if kind == "event":
                yield f"data: {_json.dumps(payload)}\n\n"
            elif kind == "error":
                yield f"data: {_json.dumps({'error': payload})}\n\n"
                return
            elif kind == "done":
                return

    return Response(
        stream_with_context(_sse_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
        },
    )


# ─────────────────────────────────────────
# ROUTES — USER MANAGEMENT
# ─────────────────────────────────────────

@app.route("/api/create-or-get-user", methods=["POST"])
def create_or_get_user():
    data         = request.json
    firebase_uid = data.get("firebase_uid")
    email        = data.get("email")
    name         = data.get("name", "User")

    if not firebase_uid or not email:
        return jsonify({"error": "firebase_uid and email are required"}), 400

    user = User.query.filter_by(firebase_uid=firebase_uid).first()
    if not user:
        user = User(firebase_uid=firebase_uid, email=email, name=name)
        db.session.add(user)
        db.session.commit()

    return jsonify({"message": "OK", "user_id": user.id})


@app.route("/api/update-user", methods=["POST"])
def update_user():
    data         = request.json
    firebase_uid = data.get("firebase_uid")
    new_name     = data.get("name")

    user = User.query.filter_by(firebase_uid=firebase_uid).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    user.name = new_name
    db.session.commit()
    return jsonify({"message": "Name updated successfully"})


@app.route("/api/delete-user/<firebase_uid>", methods=["DELETE"])
def delete_user(firebase_uid):
    user = User.query.filter_by(firebase_uid=firebase_uid).first()
    if not user:
        return jsonify({"message": "User not found"}), 404

    # Delete in order: analysis → videos → tags → user
    videos = Video.query.filter_by(user_id=user.id).all()
    for video in videos:
        if video.cloudinary_public_id:
            try:
                cloudinary.uploader.destroy(
                    video.cloudinary_public_id, resource_type="video"
                )
            except Exception as e:
                print("Cloudinary delete error:", e)
        Analysis.query.filter_by(video_id=video.id).delete()

    Video.query.filter_by(user_id=user.id).delete()
    Tag.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()

    return jsonify({"message": "User deleted successfully"})


# ─────────────────────────────────────────
# ROUTES — TAGS
# ─────────────────────────────────────────

@app.route("/api/get-tags/<firebase_uid>", methods=["GET"])
def get_tags(firebase_uid):
    decoded_token = verify_firebase_token(request)
    if not decoded_token:
        return jsonify({"error": "Unauthorized"}), 401
    if decoded_token["uid"] != firebase_uid:
        return jsonify({"error": "Forbidden"}), 403
    user = User.query.filter_by(firebase_uid=firebase_uid).first()
    if not user:
        return jsonify({"tags": []})

    tags = Tag.query.filter_by(user_id=user.id).all()
    return jsonify({"tags": [{"id": t.id, "tag_name": t.tag_name} for t in tags]})


@app.route("/api/delete-tag/<int:tag_id>", methods=["DELETE"])
def delete_tag(tag_id):
    decoded_token = verify_firebase_token(request)
    if not decoded_token:
        return jsonify({"error": "Unauthorized"}), 401
    tag = Tag.query.get(tag_id)
    if not tag:
        return jsonify({"success": False, "message": "Tag not found"}), 404

    try:
        videos = Video.query.filter_by(tag_id=tag.id).all()
        for video in videos:
            if video.cloudinary_public_id:
                try:
                    cloudinary.uploader.destroy(
                        video.cloudinary_public_id, resource_type="video"
                    )
                except Exception as e:
                    print("Cloudinary delete error:", e)
            Analysis.query.filter_by(video_id=video.id).delete()

        Video.query.filter_by(tag_id=tag.id).delete()
        db.session.delete(tag)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        print("Delete tag error:", e)
        return jsonify({"success": False})


# ─────────────────────────────────────────
# ROUTES — VIDEOS
# ─────────────────────────────────────────

@app.route("/api/get-videos/<firebase_uid>", methods=["GET"])
def get_videos(firebase_uid):
    decoded_token = verify_firebase_token(request)
    if not decoded_token:
        return jsonify({"error": "Unauthorized"}), 401
    if decoded_token["uid"] != firebase_uid:
        return jsonify({"error": "Forbidden"}), 403
    user = User.query.filter_by(firebase_uid=firebase_uid).first()
    if not user:
        return jsonify({"videos": []})

    videos = (
        Video.query
        .filter_by(user_id=user.id)
        .order_by(Video.upload_date.desc())
        .all()
    )

    return jsonify({"videos": [
        {
            "id": v.id,
            "video_title": v.video_title,
            "upload_date": v.upload_date.strftime("%d %b %Y"),
            "overall_score": v.analysis.overall_score if v.analysis else 0
        }
        for v in videos
    ]})


@app.route("/api/delete-video/<int:video_id>", methods=["DELETE"])
def delete_video(video_id):
    decoded_token = verify_firebase_token(request)
    if not decoded_token:
        return jsonify({"error": "Unauthorized"}), 401
    video = Video.query.get(video_id)
    if not video:
        return jsonify({"success": False, "message": "Video not found"}), 404

    try:
        if video.cloudinary_public_id:
            cloudinary.uploader.destroy(
                video.cloudinary_public_id, resource_type="video"
            )
        Analysis.query.filter_by(video_id=video.id).delete()
        db.session.delete(video)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        print("Delete video error:", e)
        return jsonify({"success": False})


# ─────────────────────────────────────────
# ROUTES — ANALYTICS
# ─────────────────────────────────────────

@app.route("/api/user-stats/<firebase_uid>", methods=["GET"])
def user_stats(firebase_uid):
    decoded_token = verify_firebase_token(request)
    if not decoded_token:
        return jsonify({"error": "Unauthorized"}), 401
    if decoded_token["uid"] != firebase_uid:
        return jsonify({"error": "Forbidden"}), 403
    user = User.query.filter_by(firebase_uid=firebase_uid).first()
    if not user:
        return jsonify({"tag_count": 0, "video_count": 0, "avg_score": 0})

    tag_count   = Tag.query.filter_by(user_id=user.id).count()
    video_count = Video.query.filter_by(user_id=user.id).count()

    analyses = (
        db.session.query(Analysis)
        .join(Video, Analysis.video_id == Video.id)
        .filter(Video.user_id == user.id)
        .all()
    )

    avg_score = round(
        sum(a.overall_score for a in analyses) / len(analyses), 2
    ) if analyses else 0

    return jsonify({
        "tag_count": tag_count,
        "video_count": video_count,
        "avg_score": avg_score
    })


@app.route("/api/tag-analytics", methods=["GET"])
def tag_analytics():
    decoded_token = verify_firebase_token(request)
    if not decoded_token:
        return jsonify({"error": "Unauthorized"}), 401
    firebase_uid = request.args.get("firebase_uid")
    if decoded_token["uid"] != firebase_uid:
        return jsonify({"error": "Forbidden"}), 403
   
    tag_name     = request.args.get("tag")

    if not firebase_uid or not tag_name:
        return jsonify({"videos": []})

    user = User.query.filter_by(firebase_uid=firebase_uid).first()
    if not user:
        return jsonify({"videos": []})

    tag = Tag.query.filter(
        Tag.user_id == user.id,
        Tag.tag_name.ilike(tag_name)
    ).first()
    if not tag:
        return jsonify({"videos": []})

    videos = (
        Video.query
        .filter_by(user_id=user.id, tag_id=tag.id)
        .order_by(Video.upload_date.asc())
        .all()
    )

    return jsonify({"videos": [
        {
            "id": v.id,
            "tag_id": v.tag_id,
            "title": v.video_title,
            "upload_date": v.upload_date.strftime("%d %b %Y"),
            "overall_score": v.analysis.overall_score,
            "filler_words": v.analysis.filler_words,
            "posture_score": v.analysis.posture_score,
            "eye_contact_score": v.analysis.eye_contact_score,
            "gesture_score": v.analysis.gesture_score,
            "vocabulary_score": v.analysis.vocabulary_score,
            "confidence_score": v.analysis.confidence_score,
            "topic_relevance_score": v.analysis.topic_relevance_score,
            "content_structure_score": v.analysis.content_structure_score
        }
        for v in videos if v.analysis
    ]})


# ─────────────────────────────────────────
# ROUTES — PAGE RENDERING
# ─────────────────────────────────────────

@app.route("/")
@app.route("/index")
def home():
    return render_template("index.html")

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/signup")
def signup_page():
    return render_template("signup.html")

@app.route("/new-user")
def new_user():
    return render_template("new-user.html")

@app.route("/upload")
def upload_page():
    return render_template("upload.html")

@app.route("/existing-user")
def existing_user():
    return render_template("existing-user.html")

@app.route("/editprofile-modal")
def editprofile_modal():
    return render_template("editprofile.html")

@app.route("/analysis")
def analysis():
    video_id = request.args.get("video_id")
    if not video_id:
        return "Video ID missing"

    video = Video.query.get(video_id)
    if not video or not video.analysis:
        return "Analysis not found"

    a = video.analysis

    feedback = build_feedback(
        a.speech_rate,
        a.filler_words,
        a.posture_score,
        a.eye_contact_score,
        a.gesture_score,
        a.duration or 60,
        a.vocabulary_score or 0,
        a.confidence_score or 0,
        a.topic_relevance_score or 0,
        a.content_structure_score or 0,
        a.topic_relevance_reason or "",
        a.content_structure_reason or ""
    )

    return render_template(
        "analysis.html",
        video=video,
        analysis=a,
        tag_name=video.tag.tag_name,
        feedback=feedback
    )

@app.route("/analytics")
def analytics():
    return render_template("analytics.html")


# ─────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)