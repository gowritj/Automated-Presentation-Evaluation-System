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

    // 🔹 Fetch Videos
    fetch(`/api/get-videos/${uid}`)
      .then(res => res.json())
      .then(data => {
        const videoList = document.getElementById("videoList");
        videoList.innerHTML = "";

        if (data.videos.length === 0) {
          videoList.innerHTML = "<p>No presentations uploaded yet.</p>";
          return;
        }

        data.videos.forEach(video => {
          const card = document.createElement("div");
          card.className = "video-card";

          card.innerHTML = `
            <h3>${video.video_title}</h3>
            <p>Date: ${video.upload_date}</p>
            <a href="/analysis?video_id=${video.id}" class="view-btn">
              View Analysis
            </a>
          `;

          videoList.appendChild(card);
        });
      });

    // 🔹 Fetch Stats
    fetch(`/api/user-stats/${uid}`)
  .then(res => res.json())
  .then(stats => {
    document.getElementById("videoCount").textContent = stats.video_count;
    document.getElementById("tagCount").textContent = stats.tag_count;

    document.getElementById("profileVideoCount").textContent = stats.video_count;
    document.getElementById("profileTagCount").textContent = stats.tag_count;

    document.getElementById("avgScore").textContent = stats.avg_score + "%";
  });

    // 🔹 Fetch Tags
    fetch(`/api/get-tags/${uid}`)
      .then(res => res.json())
      .then(data => {
        const tagList = document.getElementById("tagList");
        tagList.innerHTML = "";

        if (data.tags.length === 0) {
          tagList.innerHTML = "<li>No tags created yet</li>";
          return;
        }

        data.tags.forEach(tag => {
          const li = document.createElement("li");
          li.textContent = tag.tag_name;
          tagList.appendChild(li);
        });
      });

  } else {
    window.location.href = "/login";
  }
});

/* =========================
   SIDEBAR TOGGLE
========================== */

window.toggleSidebar = function () {
  const sidebar = document.getElementById("sidebar");
  const profile = document.getElementById("profilePanel");

  const isOpen = sidebar.classList.contains("active");

  // Close both first
  sidebar.classList.remove("active");
  profile.classList.remove("active");

  // Open only if it was closed
  if (!isOpen) {
    sidebar.classList.add("active");
  }
};


/* =========================
   PROFILE PANEL TOGGLE
========================== */

window.toggleProfile = function () {
  const sidebar = document.getElementById("sidebar");
  const profile = document.getElementById("profilePanel");

  const isOpen = profile.classList.contains("active");

  // Close both first
  sidebar.classList.remove("active");
  profile.classList.remove("active");

  // Open only if it was closed
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

fetch(`/api/get-tags/${uid}`)
  .then(res => res.json())
  .then(data => {
    const tagList = document.getElementById("tagList");
    tagList.innerHTML = "";

    if (data.tags.length === 0) {
      tagList.innerHTML = "<li>No tags created yet</li>";
      return;
    }

    data.tags.forEach(tag => {
      const li = document.createElement("li");
      li.textContent = tag.tag_name;
      tagList.appendChild(li);
    });
  });