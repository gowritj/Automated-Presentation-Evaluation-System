import { auth } from "./firebase.js";
import {
  signInWithEmailAndPassword,
  signInWithPopup,
  GoogleAuthProvider
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

const provider = new GoogleAuthProvider();

document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector(".login-form");
  const googleBtn = document.getElementById("googleLoginBtn");

  // EMAIL + PASSWORD LOGIN
  form.addEventListener("submit", (e) => {
    e.preventDefault();

    const email = form.querySelector('input[name="email"]').value;
    const password = form.querySelector('input[name="password"]').value;

    signInWithEmailAndPassword(auth, email, password)
      .then((userCredential) => {
        const user = userCredential.user;

        // 🔥 SAVE UID HERE
        localStorage.setItem("firebase_uid", user.uid);
        localStorage.setItem("user_email", user.email);

        window.location.href = "/existing-user";
      })
      .catch((error) => {
        alert(error.message);
      });
  });

  // GOOGLE LOGIN
  googleBtn.addEventListener("click", (e) => {
    e.preventDefault();

    signInWithPopup(auth, provider)
      .then((result) => {
        const user = result.user;

        // 🔥 SAVE UID HERE
        localStorage.setItem("firebase_uid", user.uid);
        localStorage.setItem("user_email", user.email);

        window.location.href = "/existing-user";
      })
      .catch((error) => {
        alert(error.message);
      });
  });
});