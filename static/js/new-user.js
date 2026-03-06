import { auth } from "./firebase.js";
import {
  onAuthStateChanged,
  signOut
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

onAuthStateChanged(auth, async(user) => {
  if (!user) {
    window.location.href = "/login";
  } else {
    document.getElementById("userEmail").textContent = user.email;
    document.getElementById("userName").textContent = user.displayName || "User";
     try {
      const response = await fetch(`/api/user-stats/${user.uid}`);
      const data = await response.json();

      document.getElementById("tagCount").textContent = data.tag_count;
      document.getElementById("videoCount").textContent = data.video_count;

    } catch (error) {
      console.error("Error fetching stats:", error);
    }
  }

});

// LOGOUT
window.logout = function () {
  signOut(auth).then(() => {
    window.location.href = "/";
  });
};

   //UI TOGGLES (RIGHT SIDE)

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
// LOAD EDIT PROFILE MODAL
import { loadEditProfileModal } from "./loadModal.js";

document.addEventListener("DOMContentLoaded", () => {
  loadEditProfileModal();
});