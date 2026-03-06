import { auth } from "./firebase.js";
import {
  onAuthStateChanged,
  signOut
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

/* ===============================
   WAIT FOR FIREBASE AUTH
================================= */
document.addEventListener("DOMContentLoaded", () => {
onAuthStateChanged(auth, (user) => {

  if (!user) {
    window.location.href = "/login";
    return;
  }

  const firebase_uid = user.uid;
// 🔥 Fetch user stats (update profile panel counts)
fetch(`/api/user-stats/${firebase_uid}`)
  .then(res => res.json())
  .then(stats => {

    const profileVideo = document.getElementById("profileVideoCount");
    const profileTag = document.getElementById("profileTagCount");

    if (profileVideo) {
      profileVideo.textContent = stats.video_count;
    }

    if (profileTag) {
      profileTag.textContent = stats.tag_count;
    }

  });
  const params = new URLSearchParams(window.location.search);
  const tag = params.get("tag") || "Public Speaking";

  document.getElementById("tagTitle").textContent = `Tag: ${tag}`;

  loadTagAnalytics(firebase_uid, tag);
});
});

/* ===============================
   LOAD ANALYTICS DATA
================================= */

async function loadTagAnalytics(firebase_uid, tag) {

  console.log("UID:", firebase_uid);
  console.log("Tag:", tag);

  const response = await fetch(
    `/api/tag-analytics?firebase_uid=${firebase_uid}&tag=${encodeURIComponent(tag)}`
  );

  const data = await response.json();
  console.log("API DATA:", data);

  if (!data.videos || data.videos.length === 0) {
    console.log("No videos found for this tag");
    return;
  }

  const videos = data.videos;
  const totalVideosEl = document.getElementById("totalVideos");
if (totalVideosEl) {
  totalVideosEl.textContent = videos.length;
}

  const labels = videos.map(v => v.title);
  const scores = videos.map(v => v.overall_score);
// 🔥 Calculate Average Confidence
const avgConfidence = (
  scores.reduce((a, b) => a + b, 0) / scores.length
).toFixed(2);

// 🔥 Calculate Best Performance
const bestPerformance = Math.max(...scores).toFixed(2);

// 🔥 Update Stat Cards
const avgScoreEl = document.getElementById("avgScore");
if (avgScoreEl) avgScoreEl.textContent = avgConfidence + "%";

const bestScoreEl = document.getElementById("bestScore");
if (bestScoreEl) bestScoreEl.textContent = bestPerformance + "%";
  const avgFiller = videos.reduce((a,b)=>a+b.filler_words,0)/videos.length;
  const avgPosture = videos.reduce((a,b)=>a+b.posture_score,0)/videos.length;
  const avgEye = videos.reduce((a,b)=>a+b.eye_contact_score,0)/videos.length;
  const avgGesture = videos.reduce((a,b)=>a+b.gesture_score,0)/videos.length;

  // Line Chart
  new Chart(document.getElementById("scoreChart"), {
    type: "line",
    data: {
      labels: labels,
      datasets: [{
        label: "Confidence Score",
        data: scores,
        borderColor: "#cbd5f5",
        backgroundColor: "rgba(203,213,245,0.2)",
        tension: 0.4,
        fill: true
      }]
    }
  });

  // Bar Chart
  new Chart(document.getElementById("improvementChart"), {
    type: "bar",
    data: {
      labels: ["Filler Words", "Posture", "Eye Contact", "Gestures"],
      datasets: [{
        label: "Average Performance",
        data: [avgFiller, avgPosture, avgEye, avgGesture],
        backgroundColor: "#a5b4fc"
      }]
    }
  });

  // 🔥 Render Videos Under This Tag
const videoList = document.getElementById("videoList");
videoList.innerHTML = "";

videos.forEach(video => {
  
  const card = document.createElement("div");
  card.className = "video-card";

  card.innerHTML = `
    <div class="video-card-header">
        <h3>${video.title}</h3>
        <button class="icon-btn delete-video-btn">
            <img src="../static/assests/delete.svg" alt="Delete Video">
        </button>
    </div>
    <p class="video-date">Uploaded on: ${video.upload_date}</p>
    <p class="video-score">Confidence Score: ${video.overall_score}%</p>
  `;

  // 🔥 Redirect to Analysis Page
  card.addEventListener("click", () => {
    window.location.href = `/analysis?video_id=${video.id}`;
  });

  videoList.appendChild(card);
});
}


/* ===============================
   PROFILE PANEL TOGGLE
================================= */

window.toggleProfile = function () {
  const profilePanel = document.getElementById("profilePanel");
  if (!profilePanel) return;
  profilePanel.classList.toggle("active");
};

document.addEventListener("click", (e) => {
  const profilePanel = document.getElementById("profilePanel");
  if (!profilePanel) return;

  const clickedInsideProfile = profilePanel.contains(e.target);
  const clickedProfileIcon = e.target.closest(".profile-icon");

  if (!clickedInsideProfile && !clickedProfileIcon) {
    profilePanel.classList.remove("active");
  }
});

/* ===============================
   LOGOUT FUNCTION
================================= */

window.logout = function () {
  signOut(auth)
    .then(() => {
      // Optional: clear storage
      localStorage.clear();

      window.location.href = "/login";
    })
    .catch((error) => {
      alert(error.message);
    });
};

// LOAD EDIT PROFILE MODAL
import { loadEditProfileModal } from "./loadModal.js";

document.addEventListener("DOMContentLoaded", () => {
  loadEditProfileModal();
});