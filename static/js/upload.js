// FIREBASE AUTH PROTECTION

import { auth } from "./firebase.js";
import {
  onAuthStateChanged,
  signOut
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";




const form = document.getElementById("uploadForm");
const videoInput = document.getElementById("videoInput");
const previewContainer = document.getElementById("previewContainer");
const videoPreview = document.getElementById("videoPreview");
const fileNameText = document.getElementById("fileName");
const fileUI = document.getElementById("fileUI");
const removeFileBtn = document.getElementById("removeFile");
const infoBtn = document.getElementById("infoBtn");
const infoPanel = document.getElementById("infoPanel");


//  Only one tag selection logic
const tagDropdown = document.getElementById("tagDropdown");
const newTagInput = document.getElementById("newTagInput");

// If user types new tag → clear dropdown
if (newTagInput) {
  newTagInput.addEventListener("input", () => {
    if (newTagInput.value.trim() !== "") {
      tagDropdown.value = "";
    }
  });
}

// If user selects dropdown → clear new tag input
if (tagDropdown) {
  tagDropdown.addEventListener("change", () => {
    if (tagDropdown.value !== "") {
      newTagInput.value = "";
    }
  });
}


onAuthStateChanged(auth, async (user) => {
  if (!user) {
    window.location.href = "/login";
    return;
  }

  // Update profile display
  const emailEl = document.getElementById("userEmail");
  const nameEl = document.getElementById("userName");

  if (emailEl) emailEl.textContent = user.email;
  if (nameEl) nameEl.textContent = user.displayName || "User";

  // 🔥 Fetch tags for dropdown
  try {
    const response = await fetch(`/api/get-tags/${user.uid}`);
    const data = await response.json();

    const dropdown = document.getElementById("tagDropdown");
    if (dropdown) {
      dropdown.innerHTML = `<option value="">Select existing tag</option>`;

      data.tags.forEach(tag => {
        const option = document.createElement("option");
        option.value = tag.tag_name;
        option.textContent = tag.tag_name;
        dropdown.appendChild(option);
      });
    }

  } catch (error) {
    console.error("Error loading tags:", error);
  }

  // 🔥 Fetch profile stats (to update sidebar)
  try {
    const statsRes = await fetch(`/api/user-stats/${user.uid}`);
    const stats = await statsRes.json();

    const profileTag = document.getElementById("profileTagCount");
    const profileVideo = document.getElementById("profileVideoCount");

    if (profileTag) profileTag.textContent = stats.tag_count;
    if (profileVideo) profileVideo.textContent = stats.video_count;

  } catch (error) {
    console.error("Error loading profile stats:", error);
  }
});

/* VIDEO PREVIEW */
if (videoInput) {
  videoInput.addEventListener("change", () => {
    const file = videoInput.files[0];
    if (!file) return;

    const videoURL = URL.createObjectURL(file);

    videoPreview.src = videoURL;
    fileNameText.textContent = file.name;

    previewContainer.style.display = "block";
    fileUI.style.display = "none";

    setTimeout(() => {
      const formBottom = form.getBoundingClientRect().bottom + window.scrollY;

      window.scrollTo({
        top: formBottom - window.innerHeight + 120,
        behavior: "smooth"
      });
    }, 300);

  });
}

/* REMOVE CURRENT VIDEO */
if (removeFileBtn) {
  removeFileBtn.addEventListener("click", () => {
    videoInput.value = "";
    videoPreview.src = "";
    fileNameText.textContent = "";

    previewContainer.style.display = "none";
    fileUI.style.display = "block";
  });
}


// INFO BUTTON TOGGLE


if (infoBtn) {
  infoBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    infoPanel.classList.toggle("open");
  });
}

document.addEventListener("click", (e) => {
  if (
    infoPanel &&
    !infoPanel.contains(e.target) &&
    e.target !== infoBtn
  ) {
    infoPanel.classList.remove("open");
  }
});


// PROFILE TOGGLE

const profilePanel = document.getElementById("profilePanel");

window.toggleProfile = function () {
  if (!profilePanel) return;
  profilePanel.classList.toggle("open");
};

document.addEventListener("click", (e) => {
  if (!profilePanel) return;

  const clickedInsideProfile = profilePanel.contains(e.target);
  const clickedProfileIcon = e.target.closest(".profile-icon");

  if (!clickedInsideProfile && !clickedProfileIcon) {
    profilePanel.classList.remove("open");
  }
});


// FORM SUBMIT TO BACKEND

if (form) {
  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const file = videoInput.files[0];
    if (!file) {
      alert("Please select a video first.");
      return;
    }

    const user = auth.currentUser;
    if (!user) {
      alert("User not authenticated.");
      return;
    }

    const videoTitle =
      document.getElementById("videoTitleInput")?.value || "Untitled";

    // Get tag values
    const dropdownTag = document.getElementById("tagDropdown")?.value;
    const newTag = document.getElementById("newTagInput")?.value.trim();

    // VALIDATION FIX
    if ((!newTag && !dropdownTag) || (newTag && dropdownTag)) {
      alert("Please choose either an existing tag OR create a new tag (not both).");
      return;
    }

    let selectedTag;

    if (newTag) {
      selectedTag = newTag;
    } else {
      selectedTag = dropdownTag;
    }

    const formData = new FormData();
    formData.append("video", file);
    formData.append("firebase_uid", user.uid);
    formData.append("tag_name", selectedTag);
    formData.append("video_title", videoTitle);

    try {
      //  Show uploading state
      const uploadBtn = form.querySelector(".upload-btn");
uploadBtn.disabled = true;

// Show overlay
const overlay = document.getElementById("uploadOverlay");
overlay.style.display = "flex";

      const response = await fetch(
        "/api/upload-video",
        {
          method: "POST",
          body: formData
        }
      );

      const data = await response.json();

      if (!response.ok) {
        alert(data.error || "Upload failed");
        uploadBtn.textContent = "Upload & Analyze →";
        uploadBtn.disabled = false;
        return;
      }

      // Redirect to dashboard
window.location.href = `/analysis?video_id=${data.video_id}`;
    } catch (error) {
      console.error("Upload error:", error);
      alert("Upload failed.");

      uploadBtn.textContent = "Upload & Analyze →";
      uploadBtn.disabled = false;
    }
  });
}
