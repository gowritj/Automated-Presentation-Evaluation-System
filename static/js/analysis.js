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

    // 🔹 Fetch Stats for Profile Panel
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