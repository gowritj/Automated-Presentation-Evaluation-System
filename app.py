from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from dotenv import load_dotenv
import os
import random
import cloudinary
import cloudinary.uploader

# 🔥 Load environment variables FIRST
load_dotenv()

# 🔥 Configure Cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

app = Flask(__name__)
CORS(app)

# =========================
# DATABASE CONFIG
# =========================

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "connect_args": {
        "sslmode": "require"
    }
}

db = SQLAlchemy(app)

# =========================
# MODELS
# =========================

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    firebase_uid = db.Column(db.String(200), unique=True, nullable=False)
    email = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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

# =========================
# ROUTES
# =========================

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

    # 🔥 Auto-create user if not exists
    user = User.query.filter_by(firebase_uid=firebase_uid).first()
    if not user:
        user = User(firebase_uid=firebase_uid, email=email)
        db.session.add(user)
        db.session.commit()

    # 🔥 Find or create tag
    tag = Tag.query.filter_by(user_id=user.id, tag_name=tag_name).first()
    if not tag:
        tag = Tag(tag_name=tag_name, user_id=user.id)
        db.session.add(tag)
        db.session.commit()

    # 🔥 Upload to Cloudinary (FIXED HERE)
    try:
        result = cloudinary.uploader.upload_large(
            video_file.stream,   # ✅ USE STREAM
            resource_type="video"
        )
        cloudinary_url = result["secure_url"]

    except Exception as e:
        print("CLOUDINARY ERROR:", e)
        return jsonify({"error": str(e)}), 500

    # 🔥 Save video
    new_video = Video(
        video_title=video_title,
        cloudinary_url=cloudinary_url,
        user_id=user.id,
        tag_id=tag.id
    )
    db.session.add(new_video)
    db.session.commit()

    # 🔥 Dummy Analysis
    speech_rate = round(random.uniform(120, 160), 2)
    filler_words = random.randint(5, 20)
    posture_score = round(random.uniform(60, 95), 2)
    eye_contact_score = round(random.uniform(60, 95), 2)
    gesture_score = round(random.uniform(60, 95), 2)

    overall_score = round(
        (posture_score + eye_contact_score + gesture_score) / 3,
        2
    )

    analysis = Analysis(
        video_id=new_video.id,
        speech_rate=speech_rate,
        filler_words=filler_words,
        posture_score=posture_score,
        eye_contact_score=eye_contact_score,
        gesture_score=gesture_score,
        overall_score=overall_score
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


# =========================
# PAGE ROUTES
# =========================

@app.route("/")
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


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
