// Thin wrapper over the FastAPI backend (server.py, server_class.py).

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
    throw new Error(message || `${res.status} ${res.statusText}`);
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
  doubtStart: (lid, context, section, final, cursor, question = "") =>
    request("POST", `/api/lectures/${id(lid)}/doubts/start`, { context, section, final, cursor, question }),
  // One student question on the class's single agent conversation (threadId from the previous answer, or null).
  doubtAsk: (lid, { question, context, section, final, cursor, threadId, visuals = "" }) =>
    request("POST", `/api/lectures/${id(lid)}/doubts/ask`, { question, context, section, final, cursor, thread_id: threadId, visuals }),
  doubtReply: (lid, threadId, answer) =>
    request("POST", `/api/lectures/${id(lid)}/doubts/reply`, { thread_id: threadId, answer }),
};

// Same rule as main.LECTURE_ID_RE.
export const LECTURE_ID_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{1,61}[A-Za-z0-9]$/;
