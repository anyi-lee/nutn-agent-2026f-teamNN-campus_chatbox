const state = { config: null, busy: false, draft: null, contextTeacher: null };

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const elements = {
  stage: $("#chat-stage"),
  welcome: $("#welcome"),
  messages: $("#messages"),
  form: $("#chat-form"),
  input: $("#message-input"),
  send: $("#send-button"),
  retriever: $("#retriever"),
  dialog: $("#draft-dialog"),
  draftForm: $("#draft-form"),
  draftResult: $("#draft-result"),
  teacher: $("#teacher-name"),
  purpose: $("#purpose"),
  toast: $("#toast"),
};

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.reason || data.error?.message || "請求失敗");
    error.payload = data;
    throw error;
  }
  return data;
}

async function loadConfig() {
  state.config = await request("/api/config");
  elements.teacher.innerHTML = state.config.teachers
    .map((teacher) => `<option value="${escapeHtml(teacher.name)}">${escapeHtml(teacher.name)} · ${escapeHtml(teacher.title)}</option>`)
    .join("");
  elements.purpose.innerHTML = state.config.purposes
    .map((purpose) => `<option value="${escapeHtml(purpose.value)}">${escapeHtml(purpose.label)}</option>`)
    .join("");
  $("#official-source").href = state.config.source.source_url;
  const generation = state.config.email_generation;
  const generatorStatus = $("#generator-status");
  if (generation.configuration_error === "INVALID_API_KEY_FORMAT") {
    generatorStatus.textContent = "Gemini Key 格式不正確 · 請重新啟動";
    generatorStatus.classList.remove("gemini");
  } else if (generation.configured) {
    generatorStatus.textContent = `Gemini · ${generation.model}`;
    generatorStatus.classList.add("gemini");
  } else {
    generatorStatus.textContent = "本機模板 · 尚未設定 Gemini Key";
    generatorStatus.classList.remove("gemini");
  }
}

function scrollToBottom() {
  requestAnimationFrame(() => { elements.stage.scrollTop = elements.stage.scrollHeight; });
}

function hideWelcome() {
  elements.welcome.hidden = true;
}

function addUserMessage(message) {
  elements.messages.insertAdjacentHTML("beforeend", `
    <article class="message-row user">
      <div class="message-content">${escapeHtml(message)}</div>
    </article>`);
  scrollToBottom();
}

function addTyping() {
  elements.messages.insertAdjacentHTML("beforeend", `
    <article class="message-row assistant" id="typing-row">
      <div class="avatar">AI</div>
      <div class="message-content"><div class="typing"><span></span><span></span><span></span></div></div>
    </article>`);
  scrollToBottom();
}

function retrievalTrace(retrieval) {
  if (!retrieval) return "";
  const modelLabel = retrieval.model === "bm25" ? "BM25" : "Dense Stub";
  const concepts = retrieval.query_concepts?.length
    ? `<span class="meta-chip">概念：${escapeHtml(retrieval.query_concepts.join(" · "))}</span>`
    : "";
  const rows = retrieval.candidates.map((candidate) => `
    <div class="trace-item">
      <span>#${candidate.rank}</span>
      <b>${escapeHtml(candidate.teacher_name)}</b>
      <span>${escapeHtml(candidate.score_label)} ${Number(candidate.score).toFixed(3)}</span>
    </div>`).join("");
  return `
    <div class="answer-meta"><span class="meta-chip">${modelLabel} · Top 3</span>${concepts}</div>
    <details class="trace">
      <summary>查看檢索軌跡與分數</summary>
      <div class="trace-list">${rows}</div>
    </details>`;
}

function addAssistantMessage(data) {
  $("#typing-row")?.remove();
  const isWarning = data.status !== "ok";
  const citation = data.citations?.[0];
  const source = citation
    ? `<a class="meta-chip official source-link" href="${escapeHtml(citation.url)}" target="_blank" rel="noreferrer">✓ 官方來源 · ${escapeHtml(citation.label)} ↗</a>`
    : "";
  const contextBadge = data.used_context && data.detected_teacher
    ? `<span class="meta-chip">沿用脈絡：${escapeHtml(data.detected_teacher)}老師</span>`
    : "";
  const action = data.suggested_action === "email_draft"
    ? `<button class="action-button" type="button" data-email-action data-teacher="${escapeHtml(data.detected_teacher || "")}" data-purpose="${escapeHtml(data.detected_purpose || "other")}">用這筆資料產生 Email 草稿 →</button>`
    : "";
  const id = `answer-${Date.now()}`;
  elements.messages.insertAdjacentHTML("beforeend", `
    <article class="message-row assistant" id="${id}">
      <div class="avatar">AI</div>
      <div class="message-content">
        <div class="assistant-answer ${isWarning ? "warning" : ""}">
          <p>${escapeHtml(data.answer)}</p>
          <div class="answer-meta">${source}${contextBadge}${isWarning ? `<span class="meta-chip">${escapeHtml(data.error?.code || "NEEDS_REVIEW")}</span>` : ""}</div>
          ${action}
        </div>
        ${retrievalTrace(data.retrieval)}
      </div>
    </article>`);
  $(`#${id} [data-email-action]`)?.addEventListener("click", (event) => {
    openDraft(event.currentTarget.dataset.teacher, event.currentTarget.dataset.purpose);
  });
  scrollToBottom();
}

async function sendMessage(message) {
  const cleanMessage = message.trim();
  if (!cleanMessage || state.busy) return;
  state.busy = true;
  elements.send.disabled = true;
  hideWelcome();
  addUserMessage(cleanMessage);
  elements.input.value = "";
  resizeInput();
  addTyping();
  try {
    const data = await request("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        message: cleanMessage,
        retriever: elements.retriever.value,
        context_teacher: state.contextTeacher,
      }),
    });
    if (data.detected_teacher) state.contextTeacher = data.detected_teacher;
    addAssistantMessage(data);
  } catch (error) {
    addAssistantMessage({ status: "error", answer: `目前無法完成查詢：${error.message}`, error: { code: "REQUEST_FAILED" } });
  } finally {
    state.busy = false;
    elements.send.disabled = false;
    elements.input.focus();
  }
}

function resizeInput() {
  elements.input.style.height = "auto";
  elements.input.style.height = `${Math.min(elements.input.scrollHeight, 130)}px`;
}

function openDraft(teacher = "", purpose = "other") {
  elements.draftForm.hidden = false;
  elements.draftResult.hidden = true;
  $("#form-error").textContent = "";
  if (teacher && [...elements.teacher.options].some((option) => option.value === teacher)) elements.teacher.value = teacher;
  if ([...elements.purpose.options].some((option) => option.value === purpose)) elements.purpose.value = purpose;
  elements.dialog.showModal();
}

function closeDraft() {
  elements.dialog.close();
}

async function submitDraft(event) {
  event.preventDefault();
  const submit = elements.draftForm.querySelector('[type="submit"]');
  submit.disabled = true;
  $("#form-error").textContent = "";
  const payload = Object.fromEntries(new FormData(elements.draftForm).entries());
  try {
    state.draft = await request("/api/email-draft", { method: "POST", body: JSON.stringify(payload) });
    $("#draft-to").textContent = state.draft.email_draft.to;
    $("#draft-subject").textContent = state.draft.email_draft.subject;
    $("#draft-body").textContent = state.draft.email_draft.body;
    const generation = state.draft.generation;
    $("#draft-generation-note").textContent = generation.provider === "gemini"
      ? `由 ${generation.model} 潤稿；收件人已驗證，目前尚未寄出。`
      : (generation.warning || "由本機模板產生；收件人已驗證，目前尚未寄出。");
    elements.draftForm.hidden = true;
    elements.draftResult.hidden = false;
  } catch (error) {
    $("#form-error").textContent = error.message;
  } finally {
    submit.disabled = false;
  }
}

async function copyDraft() {
  if (!state.draft) return;
  const draft = state.draft.email_draft;
  await navigator.clipboard.writeText(`收件人：${draft.to}\n主旨：${draft.subject}\n\n${draft.body}`);
  showToast("草稿已複製；系統沒有寄出郵件");
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("show");
  window.setTimeout(() => elements.toast.classList.remove("show"), 2400);
}

function resetChat() {
  elements.messages.innerHTML = "";
  elements.welcome.hidden = false;
  elements.input.value = "";
  state.contextTeacher = null;
  elements.input.focus();
}

elements.form.addEventListener("submit", (event) => { event.preventDefault(); sendMessage(elements.input.value); });
elements.input.addEventListener("input", resizeInput);
elements.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); elements.form.requestSubmit(); }
});
$$('[data-query]').forEach((button) => button.addEventListener("click", () => sendMessage(button.dataset.query)));
$("#quick-email").addEventListener("click", () => openDraft());
$("#nav-email").addEventListener("click", () => openDraft());
$("#new-chat").addEventListener("click", resetChat);
$("#dialog-close").addEventListener("click", closeDraft);
$("#cancel-draft").addEventListener("click", closeDraft);
$("#edit-draft").addEventListener("click", () => { elements.draftResult.hidden = true; elements.draftForm.hidden = false; });
$("#copy-draft").addEventListener("click", copyDraft);
elements.draftForm.addEventListener("submit", submitDraft);
elements.dialog.addEventListener("click", (event) => { if (event.target === elements.dialog) closeDraft(); });
$("#mobile-menu").addEventListener("click", () => $(".sidebar").classList.toggle("open"));

loadConfig().catch((error) => showToast(`載入設定失敗：${error.message}`));
