from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import uuid

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = "uploads/videos"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/api/upload", methods=["POST"])
def upload_video():
    if "video" not in request.files:
        return jsonify({"error": "No video file"}), 400

    video = request.files["video"]

    video_id = str(uuid.uuid4())
    filename = f"{video_id}.mp4"
    save_path = os.path.join(UPLOAD_FOLDER, filename)

    video.save(save_path)

    return jsonify({
        "message": "Video uploaded successfully",
        "video_id": video_id,
        "path": save_path
    })

@app.route("/")
def home():
    return jsonify({"status": "Backend running"})

if __name__ == "__main__":
    app.run(debug=True)
