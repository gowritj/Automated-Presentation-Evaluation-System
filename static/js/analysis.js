import { auth } from "./firebase.js";
import {
  onAuthStateChanged,
  signOut
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

/* =========================
   AUTH PROTECTION
========================== */

onAuthStateChanged(auth, (user) => {
  if (user) {

    const nameElement = document.getElementById("userName");
    const emailElement = document.getElementById("userEmail");

    if (nameElement) {
      nameElement.textContent = user.displayName || "User";
    }

    if (emailElement) {
      emailElement.textContent = user.email;
    }

    const uid = user.uid;
    const params = new URLSearchParams(window.location.search);
const videoId = params.get("d");
 
    fetch(`/api/video-analysis?video_id=${videoId}`)
  .then(res => res.json())
  .then(data => {
      console.log("Video Analysis:", data);

      // Example: Update page elements
      document.getElementById("videoTitle").textContent = data.title;
      document.getElementById("confidenceScore").textContent = data.overall_score + "%";
      document.getElementById("fillerScore").textContent = data.filler_words;
      document.getElementById("postureScore").textContent = data.posture_score;
      document.getElementById("eyeScore").textContent = data.eye_contact_score;
      document.getElementById("gestureScore").textContent = data.gesture_score;
  });
  fetch(`/api/user-stats/${uid}`)
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


  } else {
    window.location.href = "/login";
  }
});

/* =========================
   PROFILE PANEL TOGGLE
========================== */

window.toggleProfile = function () {
  const profile = document.getElementById("profilePanel");

  const isOpen = profile.classList.contains("active");

  profile.classList.remove("active");

  if (!isOpen) {
    profile.classList.add("active");
  }
};

/* =========================
   LOGOUT FUNCTION
========================== */

window.logout = function () {
  signOut(auth)
    .then(() => {
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