import { auth } from "./firebase.js";
import {
  updateProfile,
  deleteUser,
  onAuthStateChanged,
  sendPasswordResetEmail,
  EmailAuthProvider,
  reauthenticateWithCredential
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

// import {
//   getFirestore,
//   doc,
//   updateDoc,
//   deleteDoc
// } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-firestore.js";

// const db = getFirestore();

export function initEditProfileModal() {

  const modal = document.getElementById("editProfileModal");
  const openBtn = document.getElementById("openEditProfile");
  const closeBtn = document.getElementById("closeEditModal");
  const editName = document.getElementById("editName");
  const editEmail = document.getElementById("editEmail");

  let currentUser;

  if (!modal || !openBtn) return;

  openBtn.onclick = () => modal.style.display = "flex";
  closeBtn.onclick = () => modal.style.display = "none";

  window.onclick = (e) => {
    if (e.target === modal) modal.style.display = "none";
  };

  onAuthStateChanged(auth, (user) => {
    if (user) {
      currentUser = user;
      editName.value = user.displayName || "";
      editEmail.value = user.email;
    }
  });

  document
    .getElementById("editProfileForm")
    ?.addEventListener("submit", async (e) => {
      e.preventDefault();

      try {
      const newName = editName.value.trim();

if (!newName) {
  alert("Name cannot be empty.");
  return;
}

await updateProfile(currentUser, {
  displayName: newName
});

// update UI immediately
const nameElement = document.getElementById("userName");
if (nameElement) {
  nameElement.textContent = editName.value;
}

      await fetch("/api/update-user", {
  method: "POST",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    firebase_uid: currentUser.uid,
    name: editName.value
  })
});

        alert("Profile updated!");
        modal.style.display = "none";
      } catch (error) {
        alert(error.message);
      }
    });
document
  .getElementById("changePasswordBtn")
  ?.addEventListener("click", async () => {

    if (!currentUser) return;

    try {

      await sendPasswordResetEmail(auth, currentUser.email);

      alert("Password reset email sent. Check your inbox.");

    } catch (error) {
      alert(error.message);
    }

  });
  
document
.getElementById("deleteAccountBtn")
?.addEventListener("click", async () => {

  if (!currentUser) return;

  const confirmDelete = confirm(
    "This will permanently delete your account and all data."
  );

  if (!confirmDelete) return;

  try {

    const password = prompt("Enter your password to confirm deletion:");

    if (!password) {
      alert("Password required.");
      return;
    }

    const credential = EmailAuthProvider.credential(
      currentUser.email,
      password
    );

    // 1️⃣ reauthenticate
    await reauthenticateWithCredential(currentUser, credential);

    // 2️⃣ delete firebase account
    await deleteUser(currentUser);

    // 3️⃣ delete database data
    await fetch(`/api/delete-user/${currentUser.uid}`, {
      method: "DELETE"
    });

    alert("Account deleted successfully.");
    window.location.href = "/signup";

  } catch (error) {
    alert(error.message);
  }

});}