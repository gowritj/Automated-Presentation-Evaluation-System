async function autoLoadEditProfileModal() {

  const editBtn = document.getElementById("openEditProfile");
  const container = document.getElementById("modalContainer");

  // Only load modal if the page actually has the button
  if (!editBtn || !container) return;

  try {

    const response = await fetch("/editprofile-modal");
    const html = await response.text();

    container.innerHTML = html;

    const module = await import("./editprofile.js");
    module.initEditProfileModal();

  } catch (err) {
    console.error("Edit profile modal failed to load:", err);
  }

}

document.addEventListener("DOMContentLoaded", autoLoadEditProfileModal);