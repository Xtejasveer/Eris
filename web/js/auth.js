// Sign in / create an account. Teachers make courses and lessons; students join courses with a class code.

import { api } from "./api.js";
import { h, icon, avatarTint, initials } from "./ui.js";

export function renderAuth(root, onSignedIn) {
  let mode = "login", role = "student";
  const error = h("div", { class: "callout error hidden" });
  const name = h("input", { class: "input", placeholder: "Your full name", autocomplete: "name" });
  const email = h("input", { class: "input", type: "email", placeholder: "you@school.edu", autocomplete: "email" });
  const password = h("input", { class: "input", type: "password", placeholder: "At least 8 characters", autocomplete: "current-password" });
  const submitBtn = h("button", { class: "btn primary lg block", type: "submit" });
  const switchLink = h("button", { class: "link-btn", type: "button", onclick: () => { mode = mode === "login" ? "signup" : "login"; render(); } });
  const roleBtn = (value, label, ic, text) => h("button", { type: "button", class: "role-card", dataset: { role: value },
    onclick: () => { role = value; render(); } }, icon(ic), h("strong", {}, label), h("small", {}, text));
  const teacherRole = roleBtn("teacher", "I'm a teacher", "class", "Create courses and lessons");
  const roles = h("div", { class: "role-pick" },
    roleBtn("student", "I'm a student", "book", "Join a course with a class code"), teacherRole);
  // Teacher accounts may be made by the admin only: then the form offers students alone.
  let teacherSignup = false;
  api.authOptions().then((o) => { teacherSignup = !!o?.teacher_signup; render(); }, () => {});
  const nameField = h("label", { class: "field" }, h("span", {}, "Name"), name);
  const title = h("h1", {});
  const sub = h("p", { class: "muted" });

  const form = h("form", { class: "auth-form", onsubmit: async (e) => {
    e.preventDefault();
    error.classList.add("hidden");
    submitBtn.disabled = true;
    try {
      const user = mode === "login" ? await api.login(email.value, password.value, role)
        : await api.signup({ name: name.value, email: email.value, password: password.value, role });
      onSignedIn(user);
    } catch (err) {
      error.replaceChildren(icon("alert"), h("div", {}, err.message));
      error.classList.remove("hidden");
    } finally { submitBtn.disabled = false; }
  } },
    title, sub, roles, error, nameField,
    h("label", { class: "field" }, h("span", {}, "Email"), email),
    h("label", { class: "field" }, h("span", {}, "Password"), password),
    submitBtn,
    h("p", { class: "auth-switch" }, switchLink));

  // Demo accounts (python main.py seed): one click fills the form and signs in.
  const demo = h("div", { class: "demo-logins hidden" });
  api.demoLogins().then((accounts) => {
    if (!accounts?.length) return;
    const chip = (a) => h("button", { type: "button", class: "demo-chip", title: `Sign in as ${a.name}`, onclick: () => {
      mode = "login"; role = a.role; render();
      email.value = a.email; password.value = a.password;
      form.requestSubmit();
    } }, h("span", { class: "lecture-avatar", style: avatarTint(a.name) }, initials(a.name)),
      h("span", { class: "demo-text" }, h("strong", {}, a.name), h("small", {}, a.role === "teacher" ? a.subject || "Teacher" : "Student")));
    const group = (role, label) => {
      const list = accounts.filter(a => a.role === role);
      return list.length ? h("div", { class: "demo-group" }, h("small", { class: "demo-label" }, label), h("div", { class: "demo-list" }, list.map(chip))) : null;
    };
    demo.replaceChildren(h("div", { class: "demo-head" }, "Try a demo account"), group("teacher", "Teachers"), group("student", "Students"));
    demo.classList.remove("hidden");
  }, () => {});

  function render() {
    const signup = mode === "signup";
    title.textContent = signup ? "Create your account" : "Welcome back";
    if (signup && !teacherSignup) role = "student";
    sub.textContent = !signup ? "Choose who you are, then sign in to your courses."
      : teacherSignup ? "Pick who you are; you can't change it later." : "Join your course with the class code your teacher gives you.";
    roles.classList.toggle("hidden", signup && !teacherSignup);  // sign-in always asks; sign-up only when teachers may
    nameField.classList.toggle("hidden", !signup);
    roles.querySelectorAll(".role-card").forEach(b => b.classList.toggle("on", b.dataset.role === role));
    password.autocomplete = signup ? "new-password" : "current-password";
    submitBtn.textContent = signup ? "Create account" : "Sign in";
    switchLink.textContent = signup ? "Already have an account? Sign in" : "New here? Create an account";
    error.classList.add("hidden");
  }
  render();

  const tutor = h("video", { src: "assets/tutor/tutor-idle.mp4", poster: "assets/tutor/tutor-idle-poster.webp", loop: true,
    playsinline: true, autoplay: true, "aria-hidden": "true", disablepictureinpicture: true });
  tutor.muted = true;
  root.replaceChildren(h("div", { class: "auth" },
    h("section", { class: "auth-side" },
      h("div", { class: "auth-tutor" }, tutor),
      h("h2", {}, "Every lesson, ", h("span", { class: "mark" }, "on your own time"), "."),
      h("p", {}, "Your teacher's lessons, taught by their AI substitute: it explains, writes on the board and answers your doubts.")),
    h("section", { class: "auth-main" }, h("div", { class: "auth-stack" }, h("div", { class: "card auth-card" }, form), demo))));
  email.focus();
}
