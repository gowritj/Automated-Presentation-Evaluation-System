const form = document.getElementById("uploadForm");

const videoInput = document.getElementById("videoInput");
const previewContainer = document.getElementById("previewContainer");
const videoPreview = document.getElementById("videoPreview");
const fileNameText = document.getElementById("fileName");
const fileUI = document.getElementById("fileUI");

/* VIDEO PREVIEW */
videoInput.addEventListener("change", () => {
  const file = videoInput.files[0];
  if (!file) return;

  const videoURL = URL.createObjectURL(file);

  videoPreview.src = videoURL;
  fileNameText.textContent = file.name;

  previewContainer.style.display = "block";
  fileUI.style.display = "none";
});

/* UPLOAD */
form.addEventListener("submit", async (e) => {
  e.preventDefault();

  const formData = new FormData(form);

  try {
    const res = await fetch("http://127.0.0.1:5000/api/upload", {
      method: "POST",
      body: formData
    });

    const data = await res.json();

    if (!res.ok) {
      alert("Upload failed");
      return;
    }

    alert("Upload successful!");
    console.log(data);

    // later redirect:
    // window.location.href = `/processing.html?video_id=${data.video_id}`;

  } catch (err) {
    console.error(err);
    alert("Server not reachable");
  }
});
