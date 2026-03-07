import { auth } from "./firebase.js";
import {
  signInWithEmailAndPassword,
  signInWithPopup,
  GoogleAuthProvider,
  sendPasswordResetEmail
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

const provider = new GoogleAuthProvider();

document.addEventListener("DOMContentLoaded", () => {

  const form = document.querySelector(".login-form");
  const googleBtn = document.getElementById("googleLoginBtn");
  const forgotBtn = document.getElementById("forgotPassword");

  // EMAIL + PASSWORD LOGIN
  form.addEventListener("submit", (e) => {
    e.preventDefault();

    const email = form.querySelector('input[name="email"]').value;
    const password = form.querySelector('input[name="password"]').value;

    signInWithEmailAndPassword(auth, email, password)
      .then((userCredential) => {

        const user = userCredential.user;

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

        localStorage.setItem("firebase_uid", user.uid);
        localStorage.setItem("user_email", user.email);

        window.location.href = "/existing-user";

      })
      .catch((error) => {
        alert(error.message);
      });

  });

  // FORGOT PASSWORD
  forgotBtn.addEventListener("click", () => {

    const email = prompt("Enter your email to reset password:");

    if (!email) return;

    sendPasswordResetEmail(auth, email)
      .then(() => {
        alert("Password reset email sent. Check your inbox.");
      })
      .catch((error) => {
        alert(error.message);
      });

  });

});