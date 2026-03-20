from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from dotenv import load_dotenv
import os
import random
import tempfile
import shutil
import cloudinary
import cloudinary.uploader
import whisper
from moviepy import VideoFileClip
import requests
import cv2
import mediapipe as mp
import numpy as np
load_dotenv()

#  Configure Cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

app = Flask(__name__)
CORS(app)


# DATABASE CONFIG


app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "connect_args": {
        "sslmode": "require"
    }
}


db = SQLAlchemy(app)

model = whisper.load_model("tiny")
# MODELS

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


def process_video_from_cloudinary(video_url):

    # download video
    response = requests.get(video_url, stream=True)

    temp_video = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")

    for chunk in response.iter_content(chunk_size=8192):
        temp_video.write(chunk)

    temp_video.close()   # IMPORTANT: close before ffmpeg reads it
    try:
        video_path = temp_video.name
        # 🔥 NEW: posture + gesture
        posture_score = calculate_posture(video_path)
        gesture_score = calculate_gesture(video_path)
        # process video
        video = VideoFileClip(video_path)

        temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        audio_path = temp_audio.name
        temp_audio.close()
        if video.audio is None:
            duration = video.duration
            video.close()
            os.remove(video_path)
            return "", duration, True, posture_score, gesture_score   # True means silent video
        video.audio.write_audiofile(audio_path)

        audio = video.audio
        volume = audio.max_volume()

        if volume < 0.01:
            silent = True
        else:
            silent = False
        duration = video.duration
        video.close()

        result = model.transcribe(audio_path)
        text = result["text"]

        # cleanup
        
        os.remove(audio_path)

        return text, duration,silent,posture_score, gesture_score
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)


def evaluate_text(text, duration):

    words = text.split()

    word_count = len(words)

    speech_rate = word_count / (duration / 60)

    filler_list = ["um", "uh", "like", "actually", "basically"]

    filler_words = 0

    for word in filler_list:
        filler_words += text.lower().count(word)

    return speech_rate, filler_words


def calculate_posture(video_path):
    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose()

    cap = cv2.VideoCapture(video_path)

    posture_scores = []
    slouch_frames = 0
    total_frames = 0

    prev_shoulder_y = None

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        total_frames += 1

        if total_frames % 10 != 0:
            continue

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(rgb)

        if results.pose_landmarks:
            lm = results.pose_landmarks.landmark

            left_shoulder = lm[11]
            right_shoulder = lm[12]
            left_hip = lm[23]
            right_hip = lm[24]
            nose = lm[0]

            score = 0

            # -----------------------------
            # 1️⃣ Shoulder alignment (30%)
            # -----------------------------
            shoulder_diff = abs(left_shoulder.y - right_shoulder.y)

            if shoulder_diff < 0.04:
                score += 30
            elif shoulder_diff < 0.08:
                score += 15

            # -----------------------------
            # 2️⃣ Head alignment (20%)
            # -----------------------------
            mid_x = (left_shoulder.x + right_shoulder.x) / 2
            head_offset = abs(nose.x - mid_x)

            if head_offset < 0.04:
                score += 20
            elif head_offset < 0.08:
                score += 10

            # -----------------------------
            # 3️⃣ Slouch Detection (SPINE ANGLE) (30%)
            # -----------------------------
            shoulder_mid = np.array([
                (left_shoulder.x + right_shoulder.x) / 2,
                (left_shoulder.y + right_shoulder.y) / 2
            ])

            hip_mid = np.array([
                (left_hip.x + right_hip.x) / 2,
                (left_hip.y + right_hip.y) / 2
            ])

            spine_vector = hip_mid - shoulder_mid
            vertical_vector = np.array([0, 1])

            cos_angle = np.dot(spine_vector, vertical_vector) / (
                np.linalg.norm(spine_vector) * np.linalg.norm(vertical_vector) + 1e-6
            )

            angle = np.degrees(np.arccos(cos_angle))

            if angle < 10:
                score += 30
            elif angle < 20:
                score += 15
            else:
                slouch_frames += 1

           
            # 4️⃣ Lean detection (10%)
            
            lean = abs(nose.z - ((left_hip.z + right_hip.z) / 2))

            if lean < 0.1:
                score += 10
            elif lean < 0.2:
                score += 5

           
            # 5️⃣ Stability (10%)
            
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
        return 0, 0
    final_score = float(np.mean(posture_scores))
    slouch_ratio = (slouch_frames / total_frames) * 100

    #  Apply slouch penalty
  
    if slouch_ratio < 10:
        penalty = 0
    elif slouch_ratio < 30:
        penalty = 5
    elif slouch_ratio < 50:
        penalty = 10
    else:
        penalty = 20

    final_score = final_score - penalty

    # keep score within 0–100
    final_score = max(0, min(100, final_score))

    return round(final_score, 2)


def calculate_gesture(video_path):
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

        if total_frames % 10 != 0:
            continue

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb)

        current_positions = []

        if results.multi_hand_landmarks:
            gesture_frames += 1

            for hand in results.multi_hand_landmarks:
                x = hand.landmark[0].x
                y = hand.landmark[0].y
                current_positions.append(np.array([x, y]))

            # Movement tracking
        
            if prev_positions and current_positions:
                for i in range(min(len(prev_positions), len(current_positions))):
                    movement = np.linalg.norm(current_positions[i] - prev_positions[i])
                    movement_values.append(movement)

                    if movement > 0.02:
                        active_frames += 1

            # Hand spread (distance between hands)
            
            if len(current_positions) == 2:
                spread = np.linalg.norm(current_positions[0] - current_positions[1])
                spread_values.append(spread)

        prev_positions = current_positions

    cap.release()

    if total_frames == 0:
        return 0

    #  Presence Score (30%)
  
    presence_score = (gesture_frames / total_frames) * 100

    #  Movement Score (25%)

    if movement_values:
        movement_score = (active_frames / total_frames) * 100
    else:
        movement_score = 0

    # Movement Quality (20%)
   
    if movement_values:
        avg_movement = np.mean(movement_values)

        if 0.02 < avg_movement < 0.08:
            quality_score = 100   # ideal
        elif avg_movement < 0.02:
            quality_score = 40    # too static
        else:
            quality_score = 50    # too shaky
    else:
        quality_score = 0

   #Gesture Frequency (15%)
  
    frequency_score = min(100, (gesture_frames / (total_frames * 0.6)) * 100)

    # Hand Spread (10%)
   
    if spread_values:
        avg_spread = np.mean(spread_values)

        if avg_spread > 0.2:
            spread_score = 100   # expressive
        elif avg_spread > 0.1:
            spread_score = 60
        else:
            spread_score = 30    # closed hands
    else:
        spread_score = 20

    # FINAL SCORE
    
    final_score = (
        0.3 * presence_score +
        0.25 * movement_score +
        0.2 * quality_score +
        0.15 * frequency_score +
        0.1 * spread_score
    )

    return float(round(final_score, 2))


# ROUTES


@app.route("/api/upload-video", methods=["POST"])
def upload_video():

    if "video" not in request.files:
        return jsonify({"error": "No video file provided"}), 400

    video_file = request.files["video"]
    firebase_uid = request.form.get("firebase_uid")
    tag_name = request.form.get("tag_name") or "General"
    video_title = request.form.get("video_title") or "Untitled"
    email = request.form.get("email", "unknown@email.com")

    if not firebase_uid:
        return jsonify({"error": "firebase_uid missing"}), 400

    # Auto-create user if not exists
    user = User.query.filter_by(firebase_uid=firebase_uid).first()
    if not user:
        user = User(
        firebase_uid=firebase_uid,
        email=email,
        name=request.form.get("name", "User")
        )
        db.session.add(user)
        db.session.commit()

    #Find or create tag
    tag = Tag.query.filter_by(user_id=user.id, tag_name=tag_name).first()
    if not tag:
        tag = Tag(tag_name=tag_name, user_id=user.id)
        db.session.add(tag)
        db.session.commit()

    # Upload to Cloudinary (FIXED HERE)
    try:
        result = cloudinary.uploader.upload_large(
            video_file.stream,   # ✅ USE STREAM
            resource_type="video"
        )
        cloudinary_url = result["secure_url"]
        public_id = result["public_id"]

    except Exception as e:
        print("CLOUDINARY ERROR:", e)
        return jsonify({"error": str(e)}), 500

    # Save video
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

    text, duration, silent, posture_score, gesture_score = process_video_from_cloudinary(cloudinary_url)
    print("----------- EXTRACTED TEXT -----------")
    print(text)
    print("--------------------------------------")
    # Evaluate speech
    print("Evaluating text...")
    
    if silent:
        speech_rate = 0
        filler_words = 0
    else:
        speech_rate, filler_words = evaluate_text(text, duration)
    
    # Temporary body scores (still random)
    
    eye_contact_score = round(random.uniform(60, 95), 2)
   
    overall_score = round(
        (posture_score + eye_contact_score + gesture_score) / 3,
        2
    )

    analysis = Analysis(
    video_id=new_video.id,
    speech_rate=float(round(speech_rate, 2)),
    filler_words=int(filler_words),
    posture_score=float(posture_score),
    eye_contact_score=float(eye_contact_score),
    gesture_score=float(gesture_score),
    overall_score=float(overall_score)
    )

    db.session.add(analysis)
    db.session.commit()

    return jsonify({
        "message": "Upload and analysis completed",
        "video_id": new_video.id,
        "cloudinary_url": cloudinary_url,
        "tag_name": tag.tag_name,
        "overall_score": overall_score
    })
@app.route("/api/update-user", methods=["POST"])
def update_user():

    data = request.json
    firebase_uid = data.get("firebase_uid")
    new_name = data.get("name")

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

    # delete analysis
    videos = Video.query.filter_by(user_id=user.id).all()

    for video in videos:
        if video.cloudinary_public_id:
            try:
                cloudinary.uploader.destroy(
                    video.cloudinary_public_id,
                    resource_type="video"
                )
            except Exception as e:
                print("Cloudinary delete error:", e)
        Analysis.query.filter_by(video_id=video.id).delete()

    # delete videos
    Video.query.filter_by(user_id=user.id).delete()

    # delete tags
    Tag.query.filter_by(user_id=user.id).delete()

    # delete user
    db.session.delete(user)

    db.session.commit()

    return jsonify({"message": "User deleted successfully"})
#page routes
@app.route("/")
def home():
    return render_template("index.html")
@app.route("/index")
def index():
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

    return render_template(
        "analysis.html",
        video=video,
        analysis=video.analysis,
        tag_name=video.tag.tag_name   # 🔥 ADD THIS
    )
@app.route("/analytics")
def analytics():
    return render_template("analytics.html")
@app.route("/api/get-tags/<firebase_uid>", methods=["GET"])
def get_tags(firebase_uid):

    user = User.query.filter_by(firebase_uid=firebase_uid).first()

    if not user:
        return jsonify({"tags": []})

    tags = Tag.query.filter_by(user_id=user.id).all()

    tag_list = [{"id": tag.id, "tag_name": tag.tag_name} for tag in tags]

    return jsonify({"tags": tag_list})
@app.route("/api/user-stats/<firebase_uid>", methods=["GET"])
def user_stats(firebase_uid):

    user = User.query.filter_by(firebase_uid=firebase_uid).first()

    if not user:
        return jsonify({
            "tag_count": 0,
            "video_count": 0,
            "avg_score": 0
        })

    tag_count = Tag.query.filter_by(user_id=user.id).count()
    video_count = Video.query.filter_by(user_id=user.id).count()

    # 🔹 Get all analysis for this user's videos
    analyses = (
        db.session.query(Analysis)
        .join(Video, Analysis.video_id == Video.id)
        .filter(Video.user_id == user.id)
        .all()
    )

    if analyses:
        avg_score = round(
            sum(a.overall_score for a in analyses) / len(analyses),
            2
        )
    else:
        avg_score = 0

    return jsonify({
        "tag_count": tag_count,
        "video_count": video_count,
        "avg_score": avg_score
    })

@app.route("/api/get-videos/<firebase_uid>", methods=["GET"])
def get_videos(firebase_uid):

    user = User.query.filter_by(firebase_uid=firebase_uid).first()

    if not user:
        return jsonify({"videos": []})

    videos = (
        Video.query
        .filter_by(user_id=user.id)
        .order_by(Video.upload_date.desc())
        .all()
    )

    video_list = []

    for video in videos:
        video_list.append({
            "id": video.id,
            "video_title": video.video_title,
            "upload_date": video.upload_date.strftime("%d %b %Y"),
            "overall_score": video.analysis.overall_score if video.analysis else 0
        })

    return jsonify({"videos": video_list})

@app.route("/api/tag-analytics", methods=["GET"])
def tag_analytics():

    firebase_uid = request.args.get("firebase_uid")
    tag_name = request.args.get("tag")

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

    video_data = []

    for video in videos:
        if video.analysis:
            video_data.append({
    "id": video.id,
    "tag_id": video.tag_id,
    "title": video.video_title,
    "upload_date": video.upload_date.strftime("%d %b %Y"),
    "overall_score": video.analysis.overall_score,
    "filler_words": video.analysis.filler_words,
    "posture_score": video.analysis.posture_score,
    "eye_contact_score": video.analysis.eye_contact_score,
    "gesture_score": video.analysis.gesture_score
})

    return jsonify({"videos": video_data})

@app.route("/api/delete-video/<int:video_id>", methods=["DELETE"])
def delete_video(video_id):

    video = Video.query.get(video_id)

    if not video:
        return jsonify({"success": False, "message": "Video not found"}), 404

    try:

        # Delete from Cloudinary
        if video.cloudinary_public_id:
            cloudinary.uploader.destroy(
                video.cloudinary_public_id,
                resource_type="video"
            )

        # Delete analysis first
        Analysis.query.filter_by(video_id=video.id).delete()

        # Delete video
        db.session.delete(video)

        db.session.commit()

        return jsonify({"success": True})

    except Exception as e:
        print("Delete video error:", e)
        return jsonify({"success": False})
    

@app.route("/api/delete-tag/<int:tag_id>", methods=["DELETE"])
def delete_tag(tag_id):

    tag = Tag.query.get(tag_id)

    if not tag:
        return jsonify({"success": False, "message": "Tag not found"}), 404

    try:

        videos = Video.query.filter_by(tag_id=tag.id).all()

        for video in videos:

            # Delete Cloudinary video
            if video.cloudinary_public_id:
                try:
                    cloudinary.uploader.destroy(
                        video.cloudinary_public_id,
                        resource_type="video"
                    )
                except Exception as e:
                    print("Cloudinary delete error:", e)

            # Delete analysis
            Analysis.query.filter_by(video_id=video.id).delete()

        # Delete videos
        Video.query.filter_by(tag_id=tag.id).delete()

        # Delete tag
        db.session.delete(tag)

        db.session.commit()

        return jsonify({"success": True})

    except Exception as e:
        print("Delete tag error:", e)
        return jsonify({"success": False})

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)