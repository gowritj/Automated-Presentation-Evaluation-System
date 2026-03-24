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
// OVERLAY HELPERS
// ===============================
function setProgress(percent) {
  const fill = document.getElementById("progressRingFill");
  const pct  = document.getElementById("progressPct");
  if (!fill || !pct) return;
  const circumference = 314; // 2π × 50
  fill.style.strokeDashoffset = circumference - (circumference * percent / 100);
  pct.textContent = `${Math.round(percent)}%`;
}

function setStage(activeStage) {
  document.querySelectorAll(".stage-item").forEach(li => {
    const n = parseInt(li.dataset.stage, 10);
    li.classList.remove("active", "done");
    if (n < activeStage)  li.classList.add("done");
    if (n === activeStage) li.classList.add("active");
  });
}

function setMainLabel(text) {
  const el = document.getElementById("uploadMainLabel");
  if (el) el.textContent = text;
}

// ===============================
// FORM SUBMIT
// ===============================
if (form) {
  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    clearError();

    const file = videoInput.files[0];

    if (!file) { showError("Please select a video first."); return; }

    const allowedExtensions = ["mp4", "mov", "avi", "webm"];
    const fileExt = file.name.split(".").pop().toLowerCase();
    if (!allowedExtensions.includes(fileExt)) { showError("Invalid file type."); return; }
    if (!file.type.startsWith("video/"))      { showError("Invalid video file."); return; }
    if (file.size / (1024 * 1024) > 500)      { showError("File too large. Max size is 500 MB."); return; }

    const user = auth.currentUser;
    if (!user) { showError("User not authenticated."); return; }

    const videoTitle  = document.getElementById("videoTitleInput").value || "Untitled";
    const dropdownTag = tagDropdown.value;
    const newTag      = newTagInput.value.trim();

    if ((!newTag && !dropdownTag) || (newTag && dropdownTag)) {
      showError("Choose either existing tag OR new tag.");
      return;
    }

    const selectedTag = newTag || dropdownTag;
    const formData    = new FormData();
    formData.append("video",        file);
    formData.append("firebase_uid", user.uid);
    formData.append("tag_name",     selectedTag);
    formData.append("video_title",  videoTitle);

    const uploadBtn = form.querySelector(".upload-btn");
    uploadBtn.disabled = true;

    // Show overlay
    const overlay = document.getElementById("uploadOverlay");
    overlay.style.display = "flex";
    setProgress(0);
    setStage(0);
    setMainLabel("Preparing upload…");

    const token = await getAuthToken();

    // --- POST the file; read back SSE stream ---
    let fetchRes;
    try {
      fetchRes = await fetch("/api/upload-video-sse", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
    } catch (netErr) {
      overlay.style.display = "none";
      showError("Network error. Please try again.");
      uploadBtn.disabled = false;
      return;
    }

    if (!fetchRes.ok) {
      let errMsg = "Upload failed. Please try again.";
      try { const d = await fetchRes.json(); errMsg = d.error || errMsg; } catch (_) {}
      overlay.style.display = "none";
      showError(errMsg);
      uploadBtn.disabled = false;
      return;
    }

    // Parse SSE manually (fetch streams)
    const reader  = fetchRes.body.getReader();
    const decoder = new TextDecoder();
    let   buffer  = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE messages end with "\n\n"
      const messages = buffer.split("\n\n");
      buffer = messages.pop(); // keep incomplete tail

      for (const msg of messages) {
        const dataLine = msg.split("\n").find(l => l.startsWith("data:"));
        if (!dataLine) continue;

        let payload;
        try { payload = JSON.parse(dataLine.slice(5).trim()); } catch (_) { continue; }

        if (payload.error) {
          overlay.style.display = "none";
          showError(payload.error);
          uploadBtn.disabled = false;
          return;
        }

        // Update UI
        setProgress(payload.percent ?? 0);
        setMainLabel(payload.label ?? "");
        if (payload.stage) setStage(payload.stage);

        if (payload.percent === 100 && payload.video_id) {
          // Mark all stages done, then redirect
          setStage(99);
          setProgress(100);
          setMainLabel("Analysis complete! Redirecting…");
          setTimeout(() => {
            window.location.href = `/analysis?video_id=${payload.video_id}`;
          }, 600);
          return;
        }
      }
    }

    // Stream ended without a done event — something went wrong
    overlay.style.display = "none";
    showError("Processing ended unexpectedly. Please try again.");
    uploadBtn.disabled = false;
  });
}