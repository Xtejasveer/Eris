// Thin wrapper over the FastAPI backend (server.py, server_class.py, server_platform.py).

// Called when the server says the session is over (401), so the app can show the sign-in screen.
let onSignedOut = null;
export function whenSignedOut(fn) { onSignedOut = fn; }

async function request(method, path, body, { raw = false } = {}) {
  const opts = { method, headers: {} };
  if (body instanceof FormData) opts.body = body;
  else if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (raw) return res;
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    const detail = data && typeof data === "object" ? data.detail : data;
    const message = Array.isArray(detail) ? detail.map(d => d.msg).join("; ") : detail;
    if (res.status === 401 && !path.startsWith("/api/auth/")) onSignedOut?.();
    const err = new Error(message || `${res.status} ${res.statusText}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

const id = encodeURIComponent;

export const api = {
  personaTemplate: () => request("GET", "/api/persona/template"),
  lectures: () => request("GET", "/api/lectures"),
  lecture: (lid) => request("GET", `/api/lectures/${id(lid)}`),
  saveSetup: (lid, body) => request("PUT", `/api/lectures/${id(lid)}/setup`, body),
  createLecture: (lid, body) => request("POST", `/api/lectures/${id(lid)}`, body),
  upload(lid, files) {
    const form = new FormData();
    for (const f of files) form.append("files", f, f.name);
    return request("POST", `/api/lectures/${id(lid)}/files`, form);
  },
  deleteFile: (lid, name) => request("DELETE", `/api/lectures/${id(lid)}/files/${id(name)}`),
  generate: (lid, body) => request("POST", `/api/lectures/${id(lid)}/generate`, body),
  job: (lid) => request("GET", `/api/lectures/${id(lid)}/job`),
  saveScript: (lid, text) => request("PUT", `/api/lectures/${id(lid)}/script`, { text }),
  approve: (lid) => request("POST", `/api/lectures/${id(lid)}/approve`),
  reset: (lid) => request("POST", `/api/lectures/${id(lid)}/reset`),

  classData: (lid) => request("GET", `/api/lectures/${id(lid)}/class`),
  complete: (lid) => request("POST", `/api/lectures/${id(lid)}/complete`),
  tts: (lid, text) => request("POST", "/api/tts", { lecture_id: lid, text }, { raw: true }),
  ttsTiming: (lid, text) => request("POST", "/api/tts/timing", { lecture_id: lid, text }, { raw: true }),
  run: (lid, file, code) => request("POST", `/api/lectures/${id(lid)}/run`, { file, code }),
  recovery: (lid, segment, error, stateText) =>
    request("POST", `/api/lectures/${id(lid)}/recovery`, { segment, error, state_text: stateText }),
  // question: a student's question the player already collected (then the agent answers it right away).
  // lesson: {post_id, version_id} of a shared lesson a student is playing (its locked script; doubts are logged).
  doubtStart: (lid, context, section, final, cursor, question = "", lesson = {}) =>
    request("POST", `/api/lectures/${id(lid)}/doubts/start`, { context, section, final, cursor, question, ...lesson }),
  // One student question on the class's single agent conversation (threadId from the previous answer, or null).
  doubtAsk: (lid, { question, context, section, final, cursor, threadId, visuals = "", lesson = {} }) =>
    request("POST", `/api/lectures/${id(lid)}/doubts/ask`, { question, context, section, final, cursor, thread_id: threadId, visuals, ...lesson }),
  doubtReply: (lid, threadId, answer) =>
    request("POST", `/api/lectures/${id(lid)}/doubts/reply`, { thread_id: threadId, answer }),

  // ---------- accounts and courses ----------
  me: () => request("GET", "/api/auth/me"),
  demoLogins: () => request("GET", "/api/auth/demo"),
  authOptions: () => request("GET", "/api/auth/options"),
  login: (email, password) => request("POST", "/api/auth/login", { email, password }),
  signup: (body) => request("POST", "/api/auth/signup", body),
  logout: () => request("POST", "/api/auth/logout"),
  courses: () => request("GET", "/api/courses"),
  course: (cid) => request("GET", `/api/courses/${cid}`),
  createCourse: (subject, year) => request("POST", "/api/courses", { subject, year }),
  updateCourse: (cid, subject, year) => request("PUT", `/api/courses/${cid}`, { subject, year }),
  deleteCourse: (cid) => request("DELETE", `/api/courses/${cid}`),
  newCode: (cid) => request("POST", `/api/courses/${cid}/code`),
  join: (code) => request("POST", "/api/join", { code }),
  addChapter: (cid, title) => request("POST", `/api/courses/${cid}/chapters`, { title }),
  renameChapter: (chid, title) => request("PUT", `/api/chapters/${chid}`, { title }),
  deleteChapter: (chid) => request("DELETE", `/api/chapters/${chid}`),
  addTopic: (chid, title) => request("POST", `/api/chapters/${chid}/topics`, { title }),
  renameTopic: (tid, title) => request("PUT", `/api/topics/${tid}`, { title }),
  deleteTopic: (tid) => request("DELETE", `/api/topics/${tid}`),
  addLesson: (tid, body) => request("POST", `/api/topics/${tid}/lessons`, body),
  deleteLesson: (lessonId) => request("DELETE", `/api/lessons/${lessonId}`),
  share: (lessonId, note = "", dueAt = null, allowSkip = true) =>
    request("POST", `/api/lessons/${lessonId}/share`, { note, due_at: dueAt, allow_skip: allowSkip }),
  addMaterial(cid, { title, body, topicId, dueAt, files }) {
    const form = new FormData();
    form.append("title", title); form.append("body", body || "");
    form.append("topic_id", topicId ? String(topicId) : ""); form.append("due_at", dueAt || "");
    for (const f of files || []) form.append("files", f, f.name);
    return request("POST", `/api/courses/${cid}/materials`, form);
  },
  editPost: (pid, body) => request("PUT", `/api/posts/${pid}`, body),
  deletePost: (pid) => request("DELETE", `/api/posts/${pid}`),
  fileUrl: (pid, fid) => `/api/posts/${pid}/files/${fid}`,
  versions: (lessonId) => request("GET", `/api/lessons/${lessonId}/versions`),
  versionScript: (vid) => request("GET", `/api/versions/${vid}`),
  shareVersion: (lessonId, vid) => request("POST", `/api/lessons/${lessonId}/versions/${vid}/share`),
  postClass: (pid) => request("GET", `/api/posts/${pid}/class`),
  progress: (pid, body) => request("POST", `/api/posts/${pid}/progress`, body),
  feedback: (pid, body) => request("POST", `/api/posts/${pid}/feedback`, body),
  insights: (pid) => request("GET", `/api/posts/${pid}/insights`),
  resolveFeedback: (fid) => request("POST", `/api/feedback/${fid}/resolve`),
  regenerateSection: (lid, body) => request("POST", `/api/lectures/${encodeURIComponent(lid)}/regenerate-section`, body),
  attendance: (pid) => request("GET", `/api/posts/${pid}/attendance`),
  postDoubts: (pid, userId) => request("GET", `/api/posts/${pid}/doubts${userId ? `?user_id=${userId}` : ""}`),
};

// Same rule as main.LECTURE_ID_RE.
export const LECTURE_ID_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{1,61}[A-Za-z0-9]$/;
