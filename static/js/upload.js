// FIREBASE AUTH PROTECTION

import { auth } from "./firebase.js";
import {
  onAuthStateChanged,
  signOut
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

// ===============================
// ERROR HANDLING (GLOBAL)
// ===============================
const errorBox = document.getElementById("uploadError");

function showError(message) {
  if (!errorBox) return;
  errorBox.textContent = message;
  errorBox.style.display = "block";
}

function clearError() {
  if (!errorBox) return;
  errorBox.textContent = "";
  errorBox.style.display = "none";
}

// ===============================
// ELEMENTS
// ===============================
const form = document.getElementById("uploadForm");
const videoInput = document.getElementById("videoInput");
const previewContainer = document.getElementById("previewContainer");
const videoPreview = document.getElementById("videoPreview");
const fileNameText = document.getElementById("fileName");
const fileUI = document.getElementById("fileUI");
const removeFileBtn = document.getElementById("removeFile");
const infoBtn = document.getElementById("infoBtn");
const infoPanel = document.getElementById("infoPanel");

const profilePanel = document.getElementById("profilePanel");
const profileBtn = document.querySelector(".profile-icon");

const tagDropdown = document.getElementById("tagDropdown");
const newTagInput = document.getElementById("newTagInput");

// ===============================
// AUTH TOKEN
// ===============================
async function getAuthToken() {
  const user = auth.currentUser;
  if (!user) return null;
  return await user.getIdToken();
}

// ===============================
// TAG INPUT LOGIC
// ===============================
if (newTagInput) {
  newTagInput.addEventListener("input", () => {
    if (newTagInput.value.trim() !== "") {
      tagDropdown.value = "";
    }
  });
}

if (tagDropdown) {
  tagDropdown.addEventListener("change", () => {
    if (tagDropdown.value !== "") {
      newTagInput.value = "";
    }
  });
}

// ===============================
// AUTH STATE
// ===============================
onAuthStateChanged(auth, async (user) => {
  if (!user) {
    window.location.href = "/login";
    return;
  }

  document.getElementById("userEmail").textContent = user.email;
  document.getElementById("userName").textContent = user.displayName || "User";

  const token = await getAuthToken();

  // Load tags
  try {
    const res = await fetch(`/api/get-tags/${user.uid}`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    const data = await res.json();

    tagDropdown.innerHTML = `<option value="">Select existing tag</option>`;
    data.tags.forEach(tag => {
      const option = document.createElement("option");
      option.value = tag.tag_name;
      option.textContent = tag.tag_name;
      tagDropdown.appendChild(option);
    });
  } catch (err) {
    console.error(err);
  }

  // Load stats
  try {
    const res = await fetch(`/api/user-stats/${user.uid}`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    const stats = await res.json();

    document.getElementById("profileTagCount").textContent = stats.tag_count;
    document.getElementById("profileVideoCount").textContent = stats.video_count;
  } catch (err) {
    console.error(err);
  }
});

// ===============================
// VIDEO PREVIEW + VALIDATION
// ===============================
// ===============================
// VIDEO PREVIEW + VALIDATION
// ===============================
if (videoInput) {
  videoInput.addEventListener("change", () => {
    const file = videoInput.files[0];
    if (!file) return;

    clearError();

    const allowedExtensions = ["mp4", "mov", "avi", "webm"];
    const maxSizeMB = 500;

    const fileExt = file.name.split(".").pop().toLowerCase();
    const fileSizeMB = file.size / (1024 * 1024);

    // ❌ Invalid extension
    if (!allowedExtensions.includes(fileExt)) {
      showError("Invalid file type. Only MP4, MOV, AVI, WEBM allowed.");
      videoInput.value = "";
      previewContainer.style.display = "none";
      fileUI.style.display = "block";
      return;
    }

    // ❌ File too large (THIS WAS MISSING)
    if (fileSizeMB > maxSizeMB) {
      showError(`File too large. Max size is ${maxSizeMB}MB.`);
      videoInput.value = "";
      previewContainer.style.display = "none";
      fileUI.style.display = "block";
      return;
    }

    // ✅ Valid file → show preview
    const videoURL = URL.createObjectURL(file);
    videoPreview.src = videoURL;
    fileNameText.textContent = file.name;

    previewContainer.style.display = "block";
    fileUI.style.display = "none";
  });
}
// ===============================
// REMOVE VIDEO
// ===============================
if (removeFileBtn) {
  removeFileBtn.addEventListener("click", () => {
    videoInput.value = "";
    videoPreview.src = "";
    fileNameText.textContent = "";
    previewContainer.style.display = "none";
    fileUI.style.display = "block";
    clearError();
  });
}

// ===============================
// INFO PANEL
// ===============================
if (infoBtn) {
  infoBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    infoPanel.classList.toggle("open");
  });
}

document.addEventListener("click", (e) => {
  if (!infoPanel.contains(e.target) && e.target !== infoBtn) {
    infoPanel.classList.remove("open");
  }
});

// ===============================
// PROFILE PANEL
// ===============================
window.toggleProfile = function () {
  profilePanel.classList.toggle("open");
};

document.addEventListener("click", (e) => {
  if (!profilePanel.contains(e.target) && !profileBtn.contains(e.target)) {
    profilePanel.classList.remove("open");
  }
});

// ===============================
// FORM SUBMIT
// ===============================
if (form) {
  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    clearError();

    const file = videoInput.files[0];

    if (!file) {
      showError("Please select a video first.");
      return;
    }

    const allowedExtensions = ["mp4", "mov", "avi", "webm"];
    const maxSizeMB = 500;

    const fileExt = file.name.split(".").pop().toLowerCase();

    if (!allowedExtensions.includes(fileExt)) {
      showError("Invalid file type.");
      return;
    }

    if (!file.type.startsWith("video/")) {
      showError("Invalid video file.");
      return;
    }

    const fileSizeMB = file.size / (1024 * 1024);
    if (fileSizeMB > maxSizeMB) {
      showError(`File too large. Max size is ${maxSizeMB}MB.`);
      return;
    }

    const user = auth.currentUser;
    if (!user) {
      showError("User not authenticated.");
      return;
    }

    const videoTitle = document.getElementById("videoTitleInput").value || "Untitled";
    const dropdownTag = tagDropdown.value;
    const newTag = newTagInput.value.trim();

    if ((!newTag && !dropdownTag) || (newTag && dropdownTag)) {
      showError("Choose either existing tag OR new tag.");
      return;
    }

    const selectedTag = newTag || dropdownTag;

    const formData = new FormData();
    formData.append("video", file);
    formData.append("firebase_uid", user.uid);
    formData.append("tag_name", selectedTag);
    formData.append("video_title", videoTitle);

    const uploadBtn = form.querySelector(".upload-btn");

    try {
      uploadBtn.disabled = true;

      document.getElementById("uploadOverlay").style.display = "flex";

      const token = await getAuthToken();

      const res = await fetch("/api/upload-video", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData
      });

      const data = await res.json();

      if (!res.ok) {
        showError(data.error || "Upload failed");
        uploadBtn.disabled = false;
        return;
      }

      window.location.href = `/analysis?video_id=${data.video_id}`;

    } catch (err) {
      console.error(err);
      showError("Upload failed.");
      uploadBtn.disabled = false;
    }
  });
}