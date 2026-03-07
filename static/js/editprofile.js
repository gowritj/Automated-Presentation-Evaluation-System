import { auth } from "./firebase.js";
import {
  updateProfile,
  deleteUser,
  onAuthStateChanged,
  updatePassword,
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
    const passwordModal = document.getElementById("passwordModal");
const changePasswordBtn = document.getElementById("changePasswordBtn");
const closePasswordModal = document.getElementById("closePasswordModal");

changePasswordBtn.onclick = () => {
  passwordModal.style.display = "flex";
};

closePasswordModal.onclick = () => {
  passwordModal.style.display = "none";
};
document.getElementById("updatePasswordBtn")
?.addEventListener("click", async () => {

  const currentPassword =
    document.getElementById("currentPassword").value;

  const newPassword =
    document.getElementById("newPassword").value;

  const confirmPassword =
    document.getElementById("confirmPassword").value;

  if (!currentPassword || !newPassword || !confirmPassword) {
    alert("Please fill all fields.");
    return;
  }

  if (newPassword !== confirmPassword) {
    alert("Passwords do not match.");
    return;
  }

  try {

    const credential = EmailAuthProvider.credential(
      currentUser.email,
      currentPassword
    );

    // reauthenticate user
    await reauthenticateWithCredential(currentUser, credential);

    // update password
    await updatePassword(currentUser, newPassword);

    alert("Password updated successfully.");

    passwordModal.style.display = "none";

  } catch (error) {
    alert(error.message);
  }

});
// document
//   .getElementById("changePasswordBtn")
//   ?.addEventListener("click", async () => {

//     if (!currentUser) return;

//     try {

//       await sendPasswordResetEmail(auth, currentUser.email);

//       alert("Password reset email sent. Check your inbox.");

//     } catch (error) {
//       alert(error.message);
//     }

//   });
  
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

});

  // PASSWORD VISIBILITY TOGGLE
  const eyes = document.querySelectorAll(".eye");
  
  eyes.forEach(icon => {
    icon.addEventListener("click", () => {
      const targetId = icon.getAttribute("data-target");
      const input = document.getElementById(targetId);
      
      if (!input) return;
      
      if (input.type === "password") {
        input.type = "text";
        icon.src = "../static/assests/Eye off.svg";
      } else {
        input.type = "password";
        icon.src = "../static/assests/Eye.svg";
      }
    });
  });
}