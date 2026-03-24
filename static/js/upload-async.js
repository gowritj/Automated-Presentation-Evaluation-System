/**
 * upload-async.js
 * ───────────────
 * Drop-in replacement for upload.js that uses the new async endpoint
 * (/api/upload-video-async) instead of the blocking SSE route.
 *
 * Flow:
 *   1. User submits form  →  POST /api/upload-video-async
 *   2. Server returns immediately with { job_id, video_id, poll_url }
 *   3. Frontend polls /api/job-status/<job_id> every POLL_INTERVAL_MS
 *   4. Progress ring + stage list update on each PROGRESS event
 *   5. On SUCCESS → redirect to /analysis?video_id=<id>
 *   6. On FAILURE → hide overlay, show error message
 *
 * Stages map to the task's internal stage codes:
 *   cv → 1, speech → 2, groq → 3, scoring → 4, db → 5, done → 6
 */

import { auth } from "./firebase.js";
import {
  onAuthStateChanged,
  signOut,
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

// ─────────────────────────────────────────
// CONSTANTS
// ─────────────────────────────────────────

const POLL_INTERVAL_MS = 5000; // 5 seconds — matches the requirement
const MAX_POLL_RETRIES  = 180;  // 15 minutes max polling before giving up

const STAGE_MAP = {
  pending:  0,
  cv:       1,
  speech:   2,
  groq:     3,
  scoring:  4,
  db:       5,
  done:     6,
};

// ─────────────────────────────────────────
// DOM ELEMENTS
// ─────────────────────────────────────────

const errorBox         = document.getElementById("uploadError");
const form             = document.getElementById("uploadForm");
const videoInput       = document.getElementById("videoInput");
const previewContainer = document.getElementById("previewContainer");
const videoPreview     = document.getElementById("videoPreview");
const fileNameText     = document.getElementById("fileName");
const fileUI           = document.getElementById("fileUI");
const removeFileBtn    = document.getElementById("removeFile");
const infoBtn          = document.getElementById("infoBtn");
const infoPanel        = document.getElementById("infoPanel");
const profilePanel     = document.getElementById("profilePanel");
const profileBtn       = document.querySelector(".profile-icon");
const tagDropdown      = document.getElementById("tagDropdown");
const newTagInput      = document.getElementById("newTagInput");
const overlay          = document.getElementById("uploadOverlay");

// ─────────────────────────────────────────
// ERROR HELPERS
// ─────────────────────────────────────────

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

// ─────────────────────────────────────────
// AUTH
// ─────────────────────────────────────────

async function getAuthToken() {
  const user = auth.currentUser;
  if (!user) return null;
  return await user.getIdToken();
}

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
    const res  = await fetch(`/api/get-tags/${user.uid}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();

    tagDropdown.innerHTML = `<option value="">Select existing tag</option>`;
    data.tags.forEach((tag) => {
      const option       = document.createElement("option");
      option.value       = tag.tag_name;
      option.textContent = tag.tag_name;
      tagDropdown.appendChild(option);
    });
  } catch (err) {
    console.error("Tag load error:", err);
  }

  // Load stats
  try {
    const res   = await fetch(`/api/user-stats/${user.uid}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const stats = await res.json();
    document.getElementById("profileTagCount").textContent  = stats.tag_count;
    document.getElementById("profileVideoCount").textContent = stats.video_count;
  } catch (err) {
    console.error("Stats load error:", err);
  }
});

// ─────────────────────────────────────────
// TAG INPUT
// ─────────────────────────────────────────

if (newTagInput) {
  newTagInput.addEventListener("input", () => {
    if (newTagInput.value.trim() !== "") tagDropdown.value = "";
  });
}

if (tagDropdown) {
  tagDropdown.addEventListener("change", () => {
    if (tagDropdown.value !== "") newTagInput.value = "";
  });
}

// ─────────────────────────────────────────
// VIDEO PREVIEW + VALIDATION
// ─────────────────────────────────────────

if (videoInput) {
  videoInput.addEventListener("change", () => {
    const file = videoInput.files[0];
    if (!file) return;

    clearError();

    const allowedExts = ["mp4", "mov", "avi", "webm"];
    const fileExt     = file.name.split(".").pop().toLowerCase();
    const fileSizeMB  = file.size / (1024 * 1024);

    if (!allowedExts.includes(fileExt)) {
      showError("Invalid file type. Only MP4, MOV, AVI, WEBM allowed.");
      videoInput.value = "";
      previewContainer.style.display = "none";
      fileUI.style.display = "block";
      return;
    }

    if (fileSizeMB > 500) {
      showError("File too large. Max size is 500 MB.");
      videoInput.value = "";
      previewContainer.style.display = "none";
      fileUI.style.display = "block";
      return;
    }

    const videoURL       = URL.createObjectURL(file);
    videoPreview.src     = videoURL;
    fileNameText.textContent = file.name;

    previewContainer.style.display = "block";
    fileUI.style.display           = "none";
  });
}

if (removeFileBtn) {
  removeFileBtn.addEventListener("click", () => {
    videoInput.value          = "";
    videoPreview.src          = "";
    fileNameText.textContent  = "";
    previewContainer.style.display = "none";
    fileUI.style.display           = "block";
    clearError();
  });
}

// ─────────────────────────────────────────
// INFO + PROFILE PANELS
// ─────────────────────────────────────────

if (infoBtn) {
  infoBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    infoPanel.classList.toggle("open");
  });
}

document.addEventListener("click", (e) => {
  if (infoPanel && !infoPanel.contains(e.target) && e.target !== infoBtn) {
    infoPanel.classList.remove("open");
  }
});

window.toggleProfile = function () {
  profilePanel.classList.toggle("open");
};

document.addEventListener("click", (e) => {
  if (
    profilePanel &&
    profileBtn &&
    !profilePanel.contains(e.target) &&
    !profileBtn.contains(e.target)
  ) {
    profilePanel.classList.remove("open");
  }
});

// ─────────────────────────────────────────
// OVERLAY HELPERS
// ─────────────────────────────────────────

function setProgress(percent) {
  const fill = document.getElementById("progressRingFill");
  const pct  = document.getElementById("progressPct");
  if (!fill || !pct) return;
  const circumference          = 314; // 2π × 50
  fill.style.strokeDashoffset  = circumference - (circumference * percent) / 100;
  pct.textContent              = `${Math.round(percent)}%`;
}

function setStage(activeStage) {
  document.querySelectorAll(".stage-item").forEach((li) => {
    const n = parseInt(li.dataset.stage, 10);
    li.classList.remove("active", "done");
    if (n < activeStage) li.classList.add("done");
    if (n === activeStage) li.classList.add("active");
  });
}

function setMainLabel(text) {
  const el = document.getElementById("uploadMainLabel");
  if (el) el.textContent = text;
}

// ─────────────────────────────────────────
// POLLING
// ─────────────────────────────────────────

async function pollJobStatus(jobId, token, uploadBtn) {
  let retries = 0;

  return new Promise((resolve, reject) => {
    const intervalId = setInterval(async () => {
      retries++;

      if (retries > MAX_POLL_RETRIES) {
        clearInterval(intervalId);
        reject(new Error("Timed out waiting for analysis to complete."));
        return;
      }

      try {
        const res  = await fetch(`/api/job-status/${jobId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const data = await res.json();

        switch (data.state) {
          case "PENDING":
            setProgress(2);
            setMainLabel("Waiting in queue…");
            setStage(0);
            break;

          case "PROGRESS": {
            const pct   = data.percent ?? 0;
            const stage = STAGE_MAP[data.stage] ?? 1;
            setProgress(pct);
            setStage(stage);
            setMainLabel(data.label ?? "Processing…");
            break;
          }

          case "SUCCESS":
            clearInterval(intervalId);
            resolve(data.result);
            break;

          default:
            // FAILURE, REVOKED, or unknown
            clearInterval(intervalId);
            reject(new Error(data.error || "Processing failed. Please try again."));
        }
      } catch (netErr) {
        // Transient network blip — keep polling, don't abort
        console.warn("Poll error (will retry):", netErr);
      }
    }, POLL_INTERVAL_MS);
  });
}

// ─────────────────────────────────────────
// FORM SUBMIT
// ─────────────────────────────────────────

if (form) {
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearError();

    // ── Validate file ───────────────────────────────────────────────────────
    const file = videoInput.files[0];
    if (!file) { showError("Please select a video first."); return; }

    const allowedExts = ["mp4", "mov", "avi", "webm"];
    const fileExt     = file.name.split(".").pop().toLowerCase();
    if (!allowedExts.includes(fileExt)) { showError("Invalid file type."); return; }
    if (!file.type.startsWith("video/"))  { showError("Invalid video file."); return; }
    if (file.size / (1024 * 1024) > 500)  { showError("File too large. Max 500 MB."); return; }

    // ── Auth ────────────────────────────────────────────────────────────────
    const user = auth.currentUser;
    if (!user) { showError("User not authenticated."); return; }

    // ── Tag validation ──────────────────────────────────────────────────────
    const dropdownTag = tagDropdown.value;
    const newTag      = newTagInput.value.trim();
    if ((!newTag && !dropdownTag) || (newTag && dropdownTag)) {
      showError("Choose either an existing tag OR a new tag — not both.");
      return;
    }
    const selectedTag = newTag || dropdownTag;
    const videoTitle  = document.getElementById("videoTitleInput").value || "Untitled";

    // ── Build FormData ──────────────────────────────────────────────────────
    const formData = new FormData();
    formData.append("video",        file);
    formData.append("firebase_uid", user.uid);
    formData.append("tag_name",     selectedTag);
    formData.append("video_title",  videoTitle);
    formData.append("email",        user.email || "");
    formData.append("name",         user.displayName || "User");

    const uploadBtn       = form.querySelector(".upload-btn");
    uploadBtn.disabled    = true;

    // ── Show overlay ────────────────────────────────────────────────────────
    overlay.style.display = "flex";
    setProgress(0);
    setStage(0);
    setMainLabel("Uploading video…");

    const token = await getAuthToken();

    // ── POST to async endpoint ──────────────────────────────────────────────
    let jobResponse;
    try {
      const res = await fetch("/api/upload-video-async", {
        method:  "POST",
        headers: { Authorization: `Bearer ${token}` },
        body:    formData,
      });

      if (!res.ok) {
        let errMsg = "Upload failed. Please try again.";
        try { const d = await res.json(); errMsg = d.error || errMsg; } catch (_) {}
        throw new Error(errMsg);
      }

      jobResponse = await res.json();
    } catch (err) {
      overlay.style.display = "none";
      showError(err.message || "Network error. Please try again.");
      uploadBtn.disabled = false;
      return;
    }

    const { job_id, video_id } = jobResponse;

    // Cloudinary upload done — move to processing stages
    setProgress(8);
    setStage(1);
    setMainLabel("Video uploaded. Analysing…");

    // ── Poll until complete ─────────────────────────────────────────────────
    try {
      const result = await pollJobStatus(job_id, token, uploadBtn);

      setStage(6);
      setProgress(100);
      setMainLabel("Analysis complete! Redirecting…");

      setTimeout(() => {
        window.location.href = `/analysis?video_id=${result.video_id ?? video_id}`;
      }, 600);
    } catch (err) {
      overlay.style.display = "none";
      showError(err.message || "Processing failed. Please try again.");
      uploadBtn.disabled = false;
    }
  });
}
