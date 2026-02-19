import { auth } from "./firebase.js";
import {
  onAuthStateChanged,
  signOut
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

// PROTECT DASHBOARD + LOAD USER INFO
onAuthStateChanged(auth, (user) => {
  if (!user) {
    window.location.href = "/login";
  } else {
    document.getElementById("userEmail").textContent = user.email;
    document.getElementById("userName").textContent =
      user.displayName || "User";
  }
});

// LOGOUT
window.logout = function () {
  signOut(auth).then(() => {
    window.location.href = "/";
  });
};

/* =======================
   UI TOGGLES (RIGHT SIDE)
======================= */

const sidebar = document.getElementById("sidebar");
const profilePanel = document.getElementById("profilePanel");

// OPEN / CLOSE TAGS
window.toggleSidebar = function () {
  sidebar.classList.toggle("open");
  profilePanel.classList.remove("open"); // close profile
};

// OPEN / CLOSE PROFILE
window.toggleProfile = function () {
  profilePanel.classList.toggle("open");
  sidebar.classList.remove("open"); // close sidebar
};

// CLICK ANYWHERE TO CLOSE
document.addEventListener("click", (e) => {
  const clickedInsideSidebar = sidebar.contains(e.target);
  const clickedInsideProfile = profilePanel.contains(e.target);
  const clickedMenuIcon = e.target.closest(".menu-icon");
  const clickedProfileIcon = e.target.closest(".profile-icon");

  if (
    !clickedInsideSidebar &&
    !clickedInsideProfile &&
    !clickedMenuIcon &&
    !clickedProfileIcon
  ) {
    sidebar.classList.remove("open");
    profilePanel.classList.remove("open");
  }
});

