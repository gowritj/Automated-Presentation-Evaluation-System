export async function loadEditProfileModal() {

  const container = document.getElementById("modalContainer");
  if (!container) return;

  try {

    const response = await fetch("/editprofile-modal");
    const html = await response.text();

    container.innerHTML = html;

    const { initEditProfileModal } = await import("./editprofile.js");
    initEditProfileModal();

  } catch (error) {
    console.error("Modal load failed:", error);
  }
}