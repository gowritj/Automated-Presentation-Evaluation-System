import { auth } from "./firebase.js";
import {
  onAuthStateChanged,
  signOut
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

// Gets the current user's Firebase ID token for API authentication
async function getAuthToken() {
    const user = auth.currentUser;
    if (!user) return null;
    return await user.getIdToken();
}

const profilePanel = document.getElementById("profilePanel");
const profileBtn = document.querySelector(".profile-icon");

/* =========================
   AUTH PROTECTION
========================== */
onAuthStateChanged(auth, async (user) => {
  if (user) {

    const nameElement = document.getElementById("userName");
    const emailElement = document.getElementById("userEmail");

    if (nameElement) nameElement.textContent = user.displayName || "User";
    if (emailElement) emailElement.textContent = user.email;

    const uid = user.uid;
    const token = await getAuthToken();
    const params = new URLSearchParams(window.location.search);
    const videoId = params.get("video_id");

    fetch(`/api/video-analysis?video_id=${videoId}`, {
      headers: { "Authorization": `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => {
        console.log("Video Analysis:", data);
        document.getElementById("videoTitle").textContent = data.title;
        document.getElementById("confidenceScore").textContent = data.overall_score + "%";
        document.getElementById("fillerScore").textContent = data.filler_words;
        document.getElementById("postureScore").textContent = data.posture_score;
        document.getElementById("eyeScore").textContent = data.eye_contact_score;
        document.getElementById("gestureScore").textContent = data.gesture_score;
      });

    fetch(`/api/user-stats/${uid}`, {
      headers: { "Authorization": `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(stats => {
        const profileVideo = document.getElementById("profileVideoCount");
        const profileTag = document.getElementById("profileTagCount");
        if (profileVideo) profileVideo.textContent = stats.video_count;
        if (profileTag) profileTag.textContent = stats.tag_count;
      });

  } else {
    window.location.href = "/login";
  }
});

/* =========================
   PROFILE PANEL TOGGLE
========================== */
window.toggleProfile = function () {
  if (!profilePanel) return;
  const isOpen = profilePanel.classList.contains("active");
  profilePanel.classList.remove("active");
  if (!isOpen) profilePanel.classList.add("active");
};

document.addEventListener("click", (e) => {
  if (!profilePanel) return;
  const clickedInsideProfile = profilePanel.contains(e.target);
  if (!clickedInsideProfile && !profileBtn.contains(e.target)) {
    profilePanel.classList.remove("active");
  }
});

/* =========================
   LOGOUT FUNCTION
========================== */
window.logout = function () {
  signOut(auth)
    .then(() => { window.location.href = "/login"; })
    .catch((error) => { alert(error.message); });
};

import { loadEditProfileModal } from "./loadModal.js";
document.addEventListener("DOMContentLoaded", () => {
  loadEditProfileModal();
});