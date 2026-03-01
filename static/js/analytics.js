import { auth } from "./firebase.js";
import {
  onAuthStateChanged,
  signOut
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

/* ===============================
   WAIT FOR FIREBASE AUTH
================================= */

onAuthStateChanged(auth, (user) => {

  if (!user) {
    window.location.href = "/login";
    return;
  }

  const firebase_uid = user.uid;

  const params = new URLSearchParams(window.location.search);
  const tag = params.get("tag") || "Public Speaking";

  document.getElementById("tagTitle").textContent = `Tag: ${tag}`;

  loadTagAnalytics(firebase_uid, tag);
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