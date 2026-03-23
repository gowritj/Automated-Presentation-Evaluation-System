import { auth } from "./firebase.js";
import {
  onAuthStateChanged,
  signOut
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

let deleteCallback = null;

// Gets the current user's Firebase ID token for API authentication
async function getAuthToken() {
    const user = auth.currentUser;
    if (!user) return null;
    return await user.getIdToken();
}

function openDeleteModal(title, message, callback) {
  document.getElementById("deleteTitle").textContent = title;
  document.getElementById("deleteMessage").textContent = message;
  document.getElementById("deleteModal").style.display = "flex";
  deleteCallback = callback;
}

document.getElementById("cancelDelete").onclick = () => {
  document.getElementById("deleteModal").style.display = "none";
};

document.getElementById("confirmDelete").onclick = () => {
  document.getElementById("deleteModal").style.display = "none";
  if (deleteCallback) deleteCallback();
};

/* ===============================
   WAIT FOR FIREBASE AUTH
================================= */
document.addEventListener("DOMContentLoaded", () => {

  onAuthStateChanged(auth, async (user) => {

    if (!user) {
      window.location.href = "/login";
      return;
    }

    const firebase_uid = user.uid;
    const token = await getAuthToken();

    // Fetch user stats
    fetch(`/api/user-stats/${firebase_uid}`, {
      headers: { "Authorization": `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(stats => {
        const profileVideo = document.getElementById("profileVideoCount");
        const profileTag = document.getElementById("profileTagCount");
        if (profileVideo) profileVideo.textContent = stats.video_count;
        if (profileTag) profileTag.textContent = stats.tag_count;
      });

    const params = new URLSearchParams(window.location.search);
    const tag = params.get("tag") || "Public Speaking";

    document.getElementById("tagTitle").textContent = `Tag: ${tag}`;

    loadTagAnalytics(firebase_uid, tag, token);

    const deleteTagBtn = document.querySelector(".delete-tag-btn");

    deleteTagBtn.addEventListener("click", async () => {

      openDeleteModal(
        "Delete Tag",
        "This will delete the tag and all videos under it.",
        async () => {

          const freshToken = await getAuthToken();

          const response = await fetch(`/api/get-tags/${firebase_uid}`, {
            headers: { "Authorization": `Bearer ${freshToken}` }
          });
          const data = await response.json();

          const tagObj = data.tags.find(t => t.tag_name === tag);
          if (!tagObj) {
            alert("Tag not found");
            return;
          }

          const res = await fetch(`/api/delete-tag/${tagObj.id}`, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${freshToken}` }
          });

          const result = await res.json();
          if (result.success) window.location.href = "/existing-user";
        }
      );
    });

  });
});

/* ===============================
   LOAD ANALYTICS DATA
================================= */
async function loadTagAnalytics(firebase_uid, tag, token) {

  const response = await fetch(
    `/api/tag-analytics?firebase_uid=${firebase_uid}&tag=${encodeURIComponent(tag)}`,
    { headers: { "Authorization": `Bearer ${token}` } }
  );

  const data = await response.json();

  if (!data.videos || data.videos.length === 0) {
    const statsSection = document.querySelector(".performance-section");
    const chartsSection = document.querySelector(".recent-section");
    if (statsSection) statsSection.style.display = "none";
    if (chartsSection) chartsSection.style.display = "none";

    document.getElementById("videoList").innerHTML = `
      <div class="empty-state">
        <h2>Nothing under this tag yet</h2>
        <p>Upload a presentation to start tracking performance.</p>
        <a href="/upload" class="cta-upload-btn">+ Upload Presentation</a>
      </div>
    `;
    return;
  }

  const videos = data.videos;

  const statsSection = document.querySelector(".performance-section");
  const chartsSection = document.querySelector(".recent-section");
  if (statsSection) statsSection.style.display = "block";
  if (chartsSection) chartsSection.style.display = "block";

  const chartsContainer = document.querySelector(".charts-container");
  const statsContainer = document.querySelector(".stats-container");
  if (chartsContainer) chartsContainer.style.display = "grid";
  if (statsContainer) statsContainer.style.display = "flex";

  document.getElementById("totalVideos").textContent = videos.length;

  const labels = videos.map(v => v.title);
  const scores = videos.map(v => v.overall_score);

  const avgConfidence = (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(2);
  const bestPerformance = Math.max(...scores).toFixed(2);

  const avgScoreEl = document.getElementById("avgScore");
  if (avgScoreEl) avgScoreEl.textContent = avgConfidence + "%";

  const bestScoreEl = document.getElementById("bestScore");
  if (bestScoreEl) bestScoreEl.textContent = bestPerformance + "%";

  const avgFiller       = videos.reduce((a, b) => a + b.filler_words, 0) / videos.length;
  const avgPosture      = videos.reduce((a, b) => a + b.posture_score, 0) / videos.length;
  const avgEye          = videos.reduce((a, b) => a + b.eye_contact_score, 0) / videos.length;
  const avgGesture      = videos.reduce((a, b) => a + b.gesture_score, 0) / videos.length;
  const avgVocabulary      = videos.reduce((a, b) => a + b.vocabulary_score, 0) / videos.length;
  const avgConfidenceScore = videos.reduce((a, b) => a + b.confidence_score, 0) / videos.length;
  const avgTopicRel        = videos.reduce((a, b) => a + b.topic_relevance_score, 0) / videos.length;
  const avgStructure       = videos.reduce((a, b) => a + b.content_structure_score, 0) / videos.length;

  new Chart(document.getElementById("scoreChart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Overall Score",
          data: scores,
          borderColor: "#cbd5f5",
          backgroundColor: "rgba(203,213,245,0.2)",
          tension: 0.4,
          fill: true
        },
        {
          label: "Vocabulary",
          data: videos.map(v => v.vocabulary_score),
          borderColor: "#86efac",
          backgroundColor: "transparent",
          tension: 0.4
        },
        {
          label: "Confidence",
          data: videos.map(v => v.confidence_score),
          borderColor: "#fcd34d",
          backgroundColor: "transparent",
          tension: 0.4
        },
        {
          label: "Topic Relevance",
          data: videos.map(v => v.topic_relevance_score),
          borderColor: "#f9a8d4",
          backgroundColor: "transparent",
          tension: 0.4
        },
        {
          label: "Content Structure",
          data: videos.map(v => v.content_structure_score),
          borderColor: "#6ee7b7",
          backgroundColor: "transparent",
          tension: 0.4
        }
      ]
    }
  });
  new Chart(document.getElementById("improvementChart"), {
    type: "bar",
    data: {
      labels: ["Filler Words", "Posture", "Eye Contact", "Gestures", "Vocabulary", "Confidence", "Topic Relevance", "Structure"],
      datasets: [{
        label: "Average Performance",
        data: [avgFiller, avgPosture, avgEye, avgGesture, avgVocabulary, avgConfidenceScore, avgTopicRel, avgStructure],
        backgroundColor: "#a5b4fc"
      }]
    }
  });

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

    card.addEventListener("click", () => {
      window.location.href = `/analysis?video_id=${video.id}`;
    });

    card.querySelector(".delete-video-btn").addEventListener("click", (e) => {
      e.stopPropagation();

      openDeleteModal(
        "Delete Video",
        "Are you sure you want to delete this video?",
        async () => {
          const freshToken = await getAuthToken();
          const res = await fetch(`/api/delete-video/${video.id}`, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${freshToken}` }
          });
          const result = await res.json();
          if (result.success) {
            card.style.opacity = "0";
            card.style.transform = "scale(0.9)";
            setTimeout(() => card.remove(), 200);
          }
        }
      );
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
      localStorage.clear();
      window.location.href = "/login";
    })
    .catch((error) => { alert(error.message); });
};

import { loadEditProfileModal } from "./loadModal.js";
document.addEventListener("DOMContentLoaded", () => {
  loadEditProfileModal();
});