const state = { config: null, busy: false, draft: null, session: null, epoch: 0, memories: [], selectedMemories: [], appliedMemories: [], templatePreview: null, memoryOperation: null, authBusy: false };

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
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.reason || data.error?.message || "請求失敗");
    error.payload = data;
    throw error;
  }
  return data;
}

function updateSession(session) {
  if (state.session?.account?.username !== session.account?.username) clearPrivateUI();
  state.session = session;
  $("#session-status").textContent = session.context_teacher
    ? `本次對話：${session.context_teacher}老師 · 新對話會清除`
    : "本次對話未保留教師 · 僅此瀏覽器可存取";
  $("#account-status").textContent = session.account ? `已登入：${session.account.username}` : "訪客模式";
  $("#account-login").hidden = !!session.account;
  $("#account-logout").hidden = !session.account;
  $("#manage-memory").disabled = !session.account || !!state.revising || !!state.applyingDraft;
}

function clearPrivateUI() {
  state.draftWorkspaceOpen = false;
  state.revising = false;
  state.applyingDraft = false;
  lockDraftEditor(false);
  state.memories = [];
  state.selectedMemories = [];
  clearTemplateApplication();
  state.memoryOperation = null;
  state.draft = null;
  elements.dialog.close();
  elements.draftForm.reset();
  elements.input.value = "";
  elements.messages.innerHTML = "";
  ["#draft-to", "#draft-subject"].forEach(selector => { $(selector).textContent = ""; });
  ["#draft-subject-editor", "#draft-body-editor", "#memory-source-draft"].forEach(selector => { $(selector).value = ""; });
  $("#draft-letter-body").textContent = "";
  $("#saved-draft-list").textContent = "登入後可選用自己的草稿。";
  $("#revision-instructions").value = "";
  $("#revision-status").textContent = "";
  $("#memory-dialog").close();
  $("#memory-list").innerHTML = "";
  $("#draft-memory-list").textContent = "登入後可讀取自己的常用內容。";
  $("#memory-content").value = "";
  $("#memory-title").value = "";
  $("#memory-id").value = "";
  $("#memory-version").value = "";
  $("#confirm-memory").checked = false;
  Object.keys(templateFields).forEach(key => { memoryTemplateControl(key).value = ""; });
  $("#memory-kind").value = "introduction";
  toggleTemplateFields();
}

const memoryKindLabel = kind => ({introduction: "自我介紹", request: "詢問段落", signature: "署名", other: "其他", personal_fact: "個人記憶", draft_template: "草稿模板", email_template: "舊表單紀錄（不再套用）"}[kind] || kind);
const templateFields = {teacher_name: "固定教師", subject: "主旨"};
const templateControl = key => $("#template-" + key.replaceAll("_", "-"));
// Teacher is named differently in the existing draft and template forms.
const memoryTemplateControl = key => key === "teacher_name" ? $("#template-teacher") : templateControl(key);
const draftField = key => elements.draftForm.querySelector(`[name="${key}"]`);
const selectionsKey = memories => JSON.stringify(memories);
const memoryVersionMessage = "後端仍是舊版本。請在啟動服務的終端按 Ctrl+C，再執行 python app.py，並以 Ctrl+F5 重新載入；重新登入後再產生草稿。";

function memoryContractReady() {
  return state.config?.memory_contract === "private-draft-revision-v3";
}

function clearTemplateApplication() {
  state.appliedMemories = []; state.templatePreview = null;
  state.draftTemplateId = null;
  $("#draft-apply-error").textContent = "";
  $("#template-preview").hidden = true;
  $("#template-preview-text").textContent = "";
  $("#template-applied").textContent = "";
  $("#confirm-apply").checked = false;
  $("#apply-template").disabled = true;
  $("#revision-instructions").value = "";
  $("#revision-status").textContent = "";
}

function selectionChanged() {
  state.templatePreview = null;
  $("#template-preview").hidden = true;
  $("#confirm-apply").checked = false;
  $("#apply-template").disabled = true;
  $("#template-applied").textContent = "選取已變更，請先預覽並確認套用；目前表單尚未變更。";
}

function renderMemoryChoices() {
  renderSavedDraftChoices();
  const target = $("#draft-memory-list");
  if (!state.session?.account) { target.textContent = "登入後可保存與使用自己的常用文字、草稿。"; return; }
  const snippets = state.memories.filter(item => !["email_template", "draft_template", "personal_fact"].includes(item.kind));
  if (!snippets.length) { target.textContent = "尚未保存常用文字，可從側欄新增。整封信直接勾選上方已存草稿。"; return; }
  target.innerHTML = snippets.map(item => `
    <label class="memory-choice"><input type="checkbox" data-memory-choice="${escapeHtml(item.memory_id)}" ${state.selectedMemories.some(ref => ref.memory_id === item.memory_id && ref.version === item.version) ? "checked" : ""}>
    <span><b>${escapeHtml(item.title)} · ${escapeHtml(memoryKindLabel(item.kind))}</b><br>${item.kind === "draft_template" ? escapeHtml(item.template_fields.teacher_name) + " · " + escapeHtml(item.template_fields.subject) + " · 限選一份<br>" : ""}${escapeHtml(item.content)}</span></label>`).join("");
  $$("[data-memory-choice]").forEach(box => box.addEventListener("change", () => {
    state.selectedMemories = state.memories.filter(item => $$("[data-memory-choice]").some(input => input.checked && input.dataset.memoryChoice === item.memory_id))
      .map(item => ({memory_id: item.memory_id, version: item.version}));
    selectionChanged();
  }));
}

function formSnapshot() {
  return JSON.stringify(Object.fromEntries(["teacher_name", "purpose", "student_name", "student_grade", "student_department", "background", "request_details"].map(key => [key, draftField(key).value])));
}

function previewTemplateApplication() {
  $("#form-error").textContent = "";
  const memories = state.selectedMemories.map(ref => state.memories.find(item => item.memory_id === ref.memory_id && item.version === ref.version));
  if (memories.some(item => !item)) { $("#form-error").textContent = "範本已更新，請重新讀取。"; return; }
  if (memories.length > 8) { $("#form-error").textContent = "一次最多選取 8 筆常用文字。"; return; }
  const full = memories.filter(item => item.kind === "draft_template");
  if (full.length > 1) { $("#form-error").textContent = "一次只能選一份整封模板，請取消多選。"; return; }
  let reused = null;
  const snippets = memories.filter(item => item.kind !== "draft_template");
  if (full.length) {
    const fields = full[0].template_fields;
    if (!state.config.teachers.some(item => item.name === fields.teacher_name)) {
      $("#form-error").textContent = "模板的教師已失效，請先修改模板。"; return;
    }
    reused = {teacher_name: fields.teacher_name, subject: fields.subject,
      body: [full[0].content, ...snippets.map(item => item.content)].join("\n\n")};
    if (reused.body.length > 4000) { $("#form-error").textContent = "組合後正文超過 4000 字，請減少選取。"; return; }
  }
  const text = [];
  if (reused) text.push(`將建立另一封信，原表單保留。\n收件教師：${reused.teacher_name}\n主旨：${reused.subject}\n\n完整正文：\n${reused.body}`);
  else text.push("對象、目的及已填表單欄位保持原樣。");
  text.push("加入正文的文字：\n" + (snippets.map(item => `【${item.title} · ${memoryKindLabel(item.kind)}】\n${item.content}`).join("\n\n") || "（無額外段落）"));
  text.push("未勾選的內容不會加入；草稿模板直接重用文字，不交由模型重寫。套用後可修改主旨與正文，寄送仍需另行確認。");
  state.templatePreview = {reused, snapshot: formSnapshot(), key: selectionsKey(state.selectedMemories)};
  $("#template-preview-text").textContent = text.join("\n\n");
  $("#template-preview").hidden = false;
  $("#confirm-apply").checked = false;
  $("#apply-template").disabled = true;
}

function applyTemplateApplication() {
  const preview = state.templatePreview;
  if (!$("#confirm-apply").checked || !preview) return;
  if ((preview.snapshot !== null && preview.snapshot !== formSnapshot()) || preview.key !== selectionsKey(state.selectedMemories)) {
    $("#form-error").textContent = "表單或選取已變更，請重新預覽再確認。"; return;
  }
  supersedeDraftGeneration();
  state.appliedMemories = state.selectedMemories.map(ref => ({...ref}));
  state.draft = null;
  state.templatePreview = null;
  $("#template-preview").hidden = true;
  if (preview.reused) {
    elements.draftForm.hidden = true; elements.draftResult.hidden = false;
    $("#reuse-teacher").value = preview.reused.teacher_name;
    $("#draft-subject-editor").value = preview.reused.subject;
    $("#draft-body-editor").value = preview.reused.body;
    $("#draft-subject").textContent = preview.reused.subject;
    $("#draft-to").textContent = "建立草稿時重新取得官方 Email";
    $("#draft-status-title").textContent = "模板已套用，可編輯本次內容";
    $("#draft-generation-note").textContent = "直接重用已保存主旨與正文，尚未建立寄送草稿。";
    $("#tool-trace-note").textContent = "等待確認建立草稿";
    $("#confirmation-panel").hidden = true; $("#send-receipt").hidden = true;
    markDraftEdited();
    $("#draft-editor").hidden = true;
    $("#draft-letter-body").textContent = preview.reused.body;
  } else $("#template-applied").textContent = `已確認套用 ${state.appliedMemories.length} 筆文字。按「產生草稿」查看正文，尚未寄送。`;
}

function renderSavedDraftChoices() {
  const target = $("#saved-draft-list");
  if (!state.session?.account) { target.textContent = "登入後可選用自己的草稿；訪客仍可填寫下方表單建立新信。"; return; }
  const drafts = state.memories.filter(item => item.kind === "draft_template");
  const selected = state.applyingDraft ? state.pendingDraftId : state.draftTemplateId;
  target.innerHTML = drafts.length ? drafts.map(item => `<label class="memory-choice"><input type="checkbox" data-saved-draft="${escapeHtml(item.memory_id)}" ${selected === item.memory_id ? "checked" : ""} ${state.applyingDraft || state.revising ? "disabled" : ""}><span><b>${escapeHtml(item.title)}</b><br>收件教師：${escapeHtml(item.template_fields.teacher_name)}<br>主旨：${escapeHtml(item.template_fields.subject)}</span></label>`).join("") : "尚未保存完整草稿。產生信件後可按「草稿另存為模板」。";
  $$("[data-saved-draft]").forEach(box => box.addEventListener("change", () => {
    if (box.checked) applySavedDraft(box.dataset.savedDraft);
    else clearAppliedDraft();
  }));
}

function clearAppliedDraft() {
  if (state.applyingDraft || state.revising) return;
  supersedeDraftGeneration();
  state.draft = null; state.selectedMemories = [];
  clearTemplateApplication();
  $("#confirm-send").checked = false;
  $("#confirm-send").disabled = true;
  $("#send-email").disabled = true;
  elements.draftResult.hidden = true; elements.draftForm.hidden = false;
  renderMemoryChoices();
}

async function applySavedDraft(id) {
  if (state.applyingDraft || state.revising) return;
  if (!memoryContractReady()) { $("#draft-apply-error").textContent = memoryVersionMessage; return; }
  if (!state.session?.account) { $("#draft-apply-error").textContent = "請先登入才能套用自己的草稿。"; return; }
  const item = state.memories.find(item => item.memory_id === id && item.kind === "draft_template");
  if (!item) { $("#draft-apply-error").textContent = "草稿不存在或已更新，請重新讀取。"; return; }
  supersedeDraftGeneration();
  const epoch = state.epoch;
  const ref = {memory_id: item.memory_id, version: item.version};
  state.applyingDraft = true;
  state.pendingDraftId = id;
  $("#confirm-send").checked = false;
  $("#confirm-send").disabled = true;
  $("#send-email").disabled = true;
  lockDraftEditor(true); renderSavedDraftChoices();
  $("#draft-apply-error").textContent = "正在套用並驗證官方收件人……";
  try {
    const result = await sessionRequest("/api/email-template-draft", {teacher_name: item.template_fields.teacher_name,
      subject: item.template_fields.subject, body: item.content, memory_selections: [ref], confirmed: true});
    clearTemplateApplication();
    state.draftTemplateId = id;
    state.selectedMemories = [ref]; state.appliedMemories = [ref];
    renderDraft(result);
  } catch (error) { if (!error.stale) $("#draft-apply-error").textContent = error.message; }
  finally { if (epoch === state.epoch) {
    state.applyingDraft = false; state.pendingDraftId = null;
    lockDraftEditor(false); renderMemoryChoices();
    $("#confirm-send").disabled = !!state.draftDirty || !state.draft;
  } }
}

function toggleTemplateFields() {
  const full = $("#memory-kind").value === "draft_template";
  $("#memory-template-fields").hidden = !full;
  Object.keys(templateFields).forEach(key => { memoryTemplateControl(key).disabled = !full; });
  $("#memory-content").maxLength = full ? 4000 : 2000;
}

function saveDraftAsTemplate() {
  if (!memoryContractReady()) { showToast(memoryVersionMessage); return; }
  if (!state.session?.account) { showToast("請先登入，才能保存整封模板"); return; }
  if (!state.draft) { showToast("請先確認建立草稿，再另存為模板"); return; }
  editMemory();
  $("#memory-kind").value = "draft_template";
  $("#memory-title").value = "";
  $("#memory-source-draft").value = state.draft.draft_id;
  $("#memory-content").value = $("#draft-body-editor").value;
  $("#template-teacher").value = $("#reuse-teacher").value;
  $("#template-subject").value = $("#draft-subject-editor").value;
  toggleTemplateFields();
  $("#memory-dialog").showModal();
}

async function loadMemories() {
  if (!state.session?.account) { state.memories = []; renderMemoryChoices(); return; }
  const data = await sessionRequest("/api/memory/list");
  state.memories = data.memories;
  state.selectedMemories = state.selectedMemories.filter(ref => state.memories.some(item => item.memory_id === ref.memory_id && item.version === ref.version));
  renderMemoryChoices();
  $("#memory-list").innerHTML = state.memories.length ? state.memories.map(item => `
    <article class="memory-item"><strong>${escapeHtml(item.title)} · ${escapeHtml(memoryKindLabel(item.kind))} · v${item.version}</strong>
    ${item.kind === "draft_template" ? `<article class="email-paper"><dl class="mail-fields"><div><dt>收件教師</dt><dd>${escapeHtml(item.template_fields.teacher_name)}</dd></div><div><dt>主旨</dt><dd>${escapeHtml(item.template_fields.subject)}</dd></div></dl><pre>${escapeHtml(item.content)}</pre></article>` : `<p>${escapeHtml(item.content)}</p>`}<button class="button ghost" type="button" data-memory-edit="${escapeHtml(item.memory_id)}">修改／刪除</button></article>`).join("") : "尚未保存內容，可在下方新增文字，或先產生草稿再另存。";
  $$("[data-memory-edit]").forEach(button => button.addEventListener("click", () => editMemory(button.dataset.memoryEdit)));
}

function editMemory(id = "") {
  const item = state.memories.find(record => record.memory_id === id);
  $("#memory-id").value = item?.memory_id || "";
  $("#memory-version").value = item?.version || "";
  $("#memory-title").value = item?.title || "";
  $("#memory-kind").value = item?.kind === "email_template" ? "other" : (item?.kind || "introduction");
  $("#memory-source-draft").value = "";
  $("#memory-content").value = item?.content || "";
  Object.keys(templateFields).forEach(key => { memoryTemplateControl(key).value = item?.template_fields?.[key] || ""; });
  toggleTemplateFields();
  $("#confirm-memory").checked = false;
  $("#memory-delete").hidden = !item;
  $("#memory-error").textContent = "";
  state.memoryOperation = null;
  $("#memory-save").disabled = false;
  $("#memory-delete").disabled = false;
}

async function writeMemory(action) {
  if (!memoryContractReady()) { $("#memory-error").textContent = memoryVersionMessage; return; }
  if (!$("#confirm-memory").checked) { $("#memory-error").textContent = "請先勾選確認，再保存或刪除。"; return; }
  const fields = {action, confirmed: true};
  if (action !== "create") Object.assign(fields, {memory_id: $("#memory-id").value, expected_version: Number($("#memory-version").value)});
  if (action !== "delete") Object.assign(fields, {title: $("#memory-title").value, kind: $("#memory-kind").value, content: $("#memory-content").value});
  if (action !== "delete" && fields.kind === "draft_template") {
    fields.template_fields = Object.fromEntries(Object.keys(templateFields).map(key => [key, memoryTemplateControl(key).value]));
    if (action === "create") fields.source_draft_id = $("#memory-source-draft").value;
  }
  const fingerprint = JSON.stringify(fields);
  if (state.memoryOperation?.fingerprint !== fingerprint) state.memoryOperation = {fingerprint, id: crypto.randomUUID()};
  $("#memory-save").disabled = true;
  $("#memory-delete").disabled = true;
  const epoch = state.epoch;
  try {
    await sessionRequest("/api/memory/write", {...fields, operation_id: state.memoryOperation.id});
    if (state.draft?.memory_trace?.selection.some(ref => ref.memory_id === fields.memory_id)) {
      state.draft = null;
      elements.dialog.close();
      $("#draft-body-editor").value = "";
    }
    await loadMemories();
    editMemory();
    showToast(action === "delete" ? "常用內容已刪除，不再供新草稿讀取" : "已保存，可在新對話勾選套用");
  } catch (error) {
    if (!error.stale) $("#memory-error").textContent = error.message;
  } finally {
    if (epoch === state.epoch) { $("#memory-save").disabled = false; $("#memory-delete").disabled = false; }
  }
}

async function changeAccount(action, credentials = {}) {
  if (state.authBusy) return;
  state.authBusy = true;
  state.epoch += 1;
  state.busy = true;
  elements.send.disabled = true;
  $("#new-chat").disabled = true;
  clearPrivateUI();
  elements.messages.innerHTML = "";
  elements.welcome.hidden = false;
  $("#auth-error").textContent = "";
  try {
    await sessionRequest(`/api/auth/${action}`, credentials);
    $("#auth-dialog").close();
    $("#auth-password").value = "";
    await loadMemories();
    showToast(action === "logout" ? "已登出並清除本次對話；保存內容仍留在帳號內" : "已登入，可讀取自己的常用內容");
  } catch (error) {
    if (!error.stale) { $("#auth-error").textContent = error.message; showToast(`帳號操作未完成：${error.message}`); }
  } finally {
    $("#auth-password").value = "";
    state.busy = false;
    state.authBusy = false;
    $("#new-chat").disabled = false;
    elements.send.disabled = !state.session;
    $$("#auth-form button").forEach(button => { button.disabled = false; });
  }
}

async function sessionRequest(url, payload = {}) {
  if (!state.session) throw new Error("對話尚未就緒，請重新載入頁面");
  const epoch = state.epoch;
  const session = state.session;
  try {
    const data = await request(url, {
      method: "POST",
      headers: { "X-CSRF-Token": session.csrf_token },
      body: JSON.stringify({ ...payload, session_id: session.session_id, generation: session.generation }),
    });
    if (epoch !== state.epoch) throw Object.assign(new Error("舊回應已排除"), { stale: true });
    if (data.session) updateSession(data.session);
    return data;
  } catch (error) {
    if (epoch !== state.epoch) error.stale = true;
    if (!error.stale && error.payload?.session) {
      const next = error.payload.session;
      const invalidated = ["STALE_SESSION", "SOURCE_UNAVAILABLE"].includes(error.payload.error?.code)
        || next.session_id !== session.session_id
        || next.generation !== session.generation
        || next.source_version !== session.source_version
        || next.account?.username !== session.account?.username;
      updateSession(next);
      // Service errors also carry the unchanged session. Keep the dialog and
      // text on errors; invalidate only the server binding when it expired.
      if (invalidated) {
        state.draft = null;
        $("#confirm-send").checked = false;
        $("#confirm-send").disabled = true;
        $("#send-email").disabled = true;
        $("#draft-generation-note").textContent = "對話或來源已失效，請重新建立草稿。畫面文字仍保留，可先複製。";
        showToast(error.message);
      }
    }
    throw error;
  }
}

async function loadConfig() {
  state.config = await request("/api/config");
  if (!memoryContractReady()) showToast(memoryVersionMessage);
  elements.teacher.innerHTML = state.config.teachers
    .map((teacher) => `<option value="${escapeHtml(teacher.name)}">${escapeHtml(teacher.name)} · ${escapeHtml(teacher.title)}</option>`)
    .join("");
  elements.purpose.innerHTML = state.config.purposes
    .map((purpose) => `<option value="${escapeHtml(purpose.value)}">${escapeHtml(purpose.label)}</option>`)
    .join("");
  $("#template-teacher").innerHTML = '<option value="">請選擇教師</option>' + elements.teacher.innerHTML;
  $("#reuse-teacher").innerHTML = elements.teacher.innerHTML;
  renderMemoryChoices();
  $("#official-source").href = state.config.source.source_url;
  const generation = state.config.email_generation;
  const generatorStatus = $("#generator-status");
  if (generation.configuration_error === "INVALID_API_KEY_FORMAT") {
    generatorStatus.textContent = "Gemini Key 格式不正確 · 請重新啟動";
    generatorStatus.classList.remove("gemini");
  } else if (generation.configured) {
    generatorStatus.textContent = generation.backend === "langchain"
      ? `LangChain · Gemini · ${generation.model}`
      : `Manual · Gemini · ${generation.model}`;
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
  const modelLabel = retrieval.model === "bm25"
    ? "BM25"
    : (retrieval.model === "official_record" ? "Official Record" : "Dense Stub");
  const gate = retrieval.evidence_gate;
  const gateBadge = gate
    ? `<span class="meta-chip ${gate.passed ? "official" : "gate-failed"}">Evidence Gate · ${escapeHtml(gate.passed ? "PASS" : gate.failure_code)}</span>`
    : "";
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
    <div class="answer-meta"><span class="meta-chip">${modelLabel} · Top 3</span>${concepts}${gateBadge}</div>
    <details class="trace">
      <summary>查看檢索軌跡與分數</summary>
      <div class="trace-list">${rows}</div>
    </details>`;
}

function workflowTrace(workflow) {
  if (!workflow) return "";
  const label = workflow.route || workflow.stop_reason || "未決定";
  const stageRows = (workflow.stages || []).map((stage) => `
    <div class="trace-item">
      <span>${escapeHtml(stage.stage)}</span>
      <b>${escapeHtml(stage.status)}</b>
      <span>${escapeHtml(stage.branch || stage.route || stage.code || "—")}</span>
    </div>`).join("");
  return `
    <div class="answer-meta">
      <span class="meta-chip">Routing · ${escapeHtml(label)}</span>
      <span class="meta-chip">${escapeHtml(workflow.live_status || "STATUS_UNSET")}</span>
    </div>
    <details class="trace">
      <summary>查看路由決策與停止條件</summary>
      <div class="trace-list">${stageRows}</div>
    </details>`;
}

function personalMemoryChoices(candidates, id) {
  if (!state.session?.account || !candidates?.length) return "";
  return `<section class="personal-memory-choices"><h4>可加入個人記憶的資訊</h4>
    <p>以下依你本次提供的資訊整理，尚未保存。請檢查並勾選確認；相同項目會覆蓋舊值。可直接自然描述，不必套用固定句型。</p>
    ${candidates.map(item => `<label class="memory-choice"><input type="checkbox" id="personal-candidate-${escapeHtml(item.candidate_id)}">
      <span><b>${escapeHtml(item.title)}</b><br>${item.previous_content !== null ? `原記憶：${escapeHtml(item.previous_content)}<br>覆蓋為：` : "新增："}${escapeHtml(item.content)}${item.evidence_quote ? `<br>根據你說的：${escapeHtml(item.evidence_quote)}` : ""}</span></label>`).join("")}
    <button class="button ghost" type="button" id="personal-save-${id}">確認加入／覆蓋勾選的記憶</button>
    <p id="personal-status-${id}" role="status"></p></section>`;
}

async function saveChatMemories(candidates, id) {
  if (!state.session?.account) { showToast("請先登入，才能加入個人記憶。"); return; }
  const status = $(`#personal-status-${id}`), button = $(`#personal-save-${id}`);
  const selected = candidates.filter(item => {
    const box = $(`#personal-candidate-${item.candidate_id}`);
    return box.checked && !box.disabled;
  });
  if (!selected.length) { status.textContent = "請先勾選要加入或覆蓋的資訊。"; return; }
  const epoch = state.epoch;
  button.disabled = true;
  let saved = 0;
  try {
    for (const item of selected) {
      item.operation_id ||= crypto.randomUUID();
      await sessionRequest("/api/personal-memory/save", {candidate_id:item.candidate_id, confirmed:true, operation_id:item.operation_id});
      const box = $(`#personal-candidate-${item.candidate_id}`);
      box.checked = false; box.disabled = true; saved++;
    }
    status.textContent = `已加入／覆蓋 ${saved} 筆個人記憶，可在後續問答引用，或從「常用內容」管理與刪除。`;
  } catch (error) {
    if (!error.stale) status.textContent = `已保存 ${saved} 筆。${error.message}`;
  } finally { if (epoch === state.epoch) button.disabled = false; }
}

function personalMemoryTrace(analysis) {
  if (!analysis || analysis.status === "guest_disabled") return "";
  if (analysis.status === "semantic_failed_fallback") {
    return `<p>記憶語意理解暫時失敗，這次使用基本比對；未自動更改記憶。${escapeHtml(safeRevisionFailure(analysis.failure_reason))}（${escapeHtml(analysis.live_status)}）</p>`;
  }
  return `<span class="meta-chip">記憶理解：${analysis.backend === "gemini" ? "Gemini 語意判斷" : "基本比對（未設定 Gemini）"} · ${escapeHtml(analysis.live_status)}</span>`;
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
          ${personalMemoryTrace(data.personal_memory_analysis)}
          ${(data.personal_memory_used || []).map(item => `<p class="meta-chip">使用你的記憶：${escapeHtml(item.title)} → ${escapeHtml(item.content)}（非官方證明）</p>`).join("")}
          ${personalMemoryChoices(data.personal_memory_candidates, id)}
        </div>
        ${workflowTrace(data.workflow)}
        ${retrievalTrace(data.retrieval)}
      </div>
    </article>`);
  $(`#${id} [data-email-action]`)?.addEventListener("click", (event) => {
    openDraft(event.currentTarget.dataset.teacher, event.currentTarget.dataset.purpose);
  });
  if (data.personal_memory_candidates?.length && state.session?.account) {
    $(`#personal-save-${id}`).addEventListener("click", () => saveChatMemories(data.personal_memory_candidates, id));
  }
  scrollToBottom();
}

async function sendMessage(message) {
  const cleanMessage = message.trim();
  if (!cleanMessage || state.busy) return;
  state.busy = true;
  const epoch = state.epoch;
  elements.send.disabled = true;
  hideWelcome();
  addUserMessage(cleanMessage);
  elements.input.value = "";
  resizeInput();
  addTyping();
  try {
    const data = await sessionRequest("/api/chat", {
      message: cleanMessage, retriever: elements.retriever.value,
    });
    addAssistantMessage(data);
  } catch (error) {
    if (error.stale) return;
    addAssistantMessage({ status: "error", answer: `目前無法完成查詢：${error.message}`, error: { code: "REQUEST_FAILED" } });
  } finally {
    if (epoch === state.epoch) {
      state.busy = false;
      elements.send.disabled = false;
      elements.input.focus();
    }
  }
}

function resizeInput() {
  elements.input.style.height = "auto";
  elements.input.style.height = `${Math.min(elements.input.scrollHeight, 130)}px`;
}

async function openDraft(teacher = "", purpose = "other") {
  $("#confirm-send").checked = false;
  $("#send-email").disabled = true;
  if (state.draftWorkspaceOpen) {
    elements.dialog.showModal();
    try { await loadMemories(); } catch (error) { if (!error.stale) showToast(error.message); }
    return;
  }
  state.draftWorkspaceOpen = true;
  elements.draftForm.hidden = false;
  elements.draftResult.hidden = true;
  state.draft = null;
  state.selectedMemories = [];
  clearTemplateApplication();
  $("#form-error").textContent = "";
  if (teacher && [...elements.teacher.options].some((option) => option.value === teacher)) elements.teacher.value = teacher;
  if ([...elements.purpose.options].some((option) => option.value === purpose)) elements.purpose.value = purpose;
  elements.dialog.showModal();
  try { await loadMemories(); } catch (error) { if (!error.stale) $("#form-error").textContent = error.message; }
}

function closeDraft() {
  $("#confirm-send").checked = false;
  $("#send-email").disabled = true;
  elements.dialog.close();
}

function lockDraftEditor(locked) {
  const blocked = locked || !!state.revising || !!state.applyingDraft;
  ["#reuse-teacher", "#draft-subject-editor", "#draft-body-editor", "#edit-email-content", "#revision-instructions", "#revise-email", "#update-draft", "#save-draft-template", "#edit-draft", "#nav-email", "#quick-email"].forEach(selector => { $(selector).disabled = blocked; });
  $$("[data-saved-draft]").forEach(box => { box.disabled = blocked; });
  $("#manage-memory").disabled = blocked || !state.session?.account;
  elements.draftForm.querySelector('[type="submit"]').disabled = blocked;
}

function markDraftEdited() {
  state.draftDirty = true;
  $("#confirm-send").checked = false;
  $("#confirm-send").disabled = true;
  $("#send-email").disabled = true;
  $("#update-draft").hidden = false;
  $("#update-draft").textContent = state.draft ? "確認修改並更新草稿" : "確認建立新草稿";
  $("#draft-edit-note").textContent = "請先確認建立／更新草稿，重新驗證官方收件人，再確認寄送。";
  $("#draft-letter-body").textContent = $("#draft-body-editor").value;
  $("#draft-subject").textContent = $("#draft-subject-editor").value;
  lockDraftEditor(false);
}

function renderDraft(result) {
  state.draftWorkspaceOpen = true;
  state.draft = result;
  state.draftDirty = false;
  lockDraftEditor(false);
  $("#reuse-teacher").value = result.teacher.teacher_name;
  $("#draft-to").textContent = result.email_draft.to;
  $("#draft-subject").textContent = result.email_draft.subject;
  $("#draft-subject-editor").value = result.email_draft.subject;
  $("#draft-body-editor").value = result.email_draft.body;
  $("#draft-letter-body").textContent = result.email_draft.body;
  $("#draft-editor").hidden = true;
  $("#draft-status-title").textContent = "草稿已建立";
  $("#tool-trace-note").textContent = result.generation.provider === "gemini"
    ? (result.generation.backend === "langchain" ? "LANGCHAIN · create_agent → get_teacher_contact · passed" : "GEMINI · functionCall → functionResponse · passed")
    : "HOST · get_teacher_contact · found";
  $("#confirm-send").checked = false;
  $("#confirm-send").disabled = false;
  $("#confirmation-panel").hidden = false;
  $("#send-email").disabled = true;
  $("#send-email").textContent = "確認並模擬寄出";
  $("#send-receipt").hidden = true;
  $("#send-error").textContent = "";
  $("#update-draft").hidden = true;
  $("#draft-edit-note").textContent = "可直接編輯主旨與正文；任何修改都需要更新草稿及重新確認寄送。";
  const generation = result.generation;
  $("#draft-generation-note").textContent = generation.provider === "saved_draft"
    ? "保留你確認的主旨與正文，未交由模型重寫；已重新驗證官方收件人，目前尚未寄送。"
    : generation.provider === "gemini"
      ? `由 ${generation.backend === "langchain" ? "LangChain + " : ""}${generation.model} 潤稿；收件人已驗證，目前尚未寄出。`
      : (generation.warning || "由本機模板產生；收件人已驗證，目前尚未寄出。");
  elements.draftForm.hidden = true;
  elements.draftResult.hidden = false;
}

async function updateEditedDraft() {
  supersedeDraftGeneration();
  const button = $("#update-draft");
  const epoch = state.epoch;
  const payload = {teacher_name: $("#reuse-teacher").value, subject: $("#draft-subject-editor").value,
    body: $("#draft-body-editor").value, confirmed: true};
  if (state.draft) payload.source_draft_id = state.draft.draft_id;
  else Object.assign(payload, {memory_selections: state.appliedMemories});
  button.disabled = true; lockDraftEditor(true);
  $("#send-error").textContent = "";
  try {
    const result = await sessionRequest(state.draft ? "/api/email-draft-edit" : "/api/email-template-draft", payload);
    renderDraft(result);
  } catch (error) { if (!error.stale) $("#send-error").textContent = error.message; }
  finally { if (epoch === state.epoch) { button.disabled = false; lockDraftEditor(false); } }
}

function safeRevisionFailure(reason) {
  if (typeof reason !== "string") return "";
  return reason
    .replace(/AIza[\w-]+/g, "[已遮蔽金鑰]")
    .replace(/Bearer\s+[^\s,;"']+/gi, "Bearer [已遮蔽]")
    .replace(/((?:x-goog-api-key|api[_-]?key|access[_-]?token|refresh[_-]?token)\s*[=:]\s*)[^\s,;&"']+/gi, "$1[已遮蔽]")
    .replace(/[\r\n\t]+/g, " ")
    .slice(0, 500).trim();
}

async function reviseDraftWithAI() {
  if (state.revising || state.applyingDraft) return;
  if (!memoryContractReady()) { $("#revision-status").textContent = memoryVersionMessage; return; }
  const instructions = $("#revision-instructions").value.trim();
  if (!state.draft) { $("#revision-status").textContent = "請先引用或產生一份草稿。"; return; }
  if (!instructions || instructions.length > 1000) { $("#revision-status").textContent = "請填寫 1–1000 字的調整指示。"; return; }
  supersedeDraftGeneration();
  const epoch = state.epoch;
  state.revising = true;
  $("#confirm-send").checked = false;
  $("#confirm-send").disabled = true;
  $("#send-email").disabled = true;
  lockDraftEditor(true);
  $("#revision-status").textContent = "AI 調整中，完成後請重新檢查全文與收件人……";
  try {
    // Include any manual edits by first creating their canonical server draft.
    if (state.draftDirty) {
      await updateEditedDraft();
      if (epoch !== state.epoch) return;
      if (state.draftDirty || !state.draft) { $("#revision-status").textContent = "手動修改尚未更新成功，未呼叫 AI。"; return; }
    }
    $("#confirm-send").disabled = true;
    const result = await sessionRequest("/api/email-draft-revise", {source_draft_id: state.draft.draft_id, instructions});
    renderDraft(result);
    $("#revision-status").textContent = "AI 已產生新版草稿，原保存模板未變更。請檢查新內容，並重新確認寄送。";
  } catch (error) {
    if (!error.stale) {
      const detail = safeRevisionFailure(error.payload?.generation?.failure_reason);
      $("#revision-status").textContent = `${error.message}（${error.payload?.generation?.evidence_status || "未完成"}）${detail ? ` 原因：${detail}` : ""}`;
    }
  } finally {
    if (epoch === state.epoch) {
      state.revising = false;
      lockDraftEditor(false);
      $("#confirm-send").checked = false;
      $("#confirm-send").disabled = !!state.draftDirty || !state.draft;
      $("#send-email").disabled = true;
    }
  }
}

function supersedeDraftGeneration() {
  state.draftGeneration = (state.draftGeneration || 0) + 1;
  elements.draftForm.querySelector('[type="submit"]').disabled = false;
  return state.draftGeneration;
}

async function submitDraft(event) {
  event.preventDefault();
  if (state.applyingDraft || state.revising) return;
  if (selectionsKey(state.selectedMemories) !== selectionsKey(state.appliedMemories)) {
    $("#form-error").textContent = "選取已變更，請先預覽並確認套用，再產生草稿。"; return;
  }
  const epoch = state.epoch;
  const draftGeneration = supersedeDraftGeneration();
  const submit = elements.draftForm.querySelector('[type="submit"]');
  submit.disabled = true;
  $("#form-error").textContent = "";
  const payload = Object.fromEntries(new FormData(elements.draftForm).entries());
  payload.memory_selections = state.appliedMemories;
  try {
    const result = await sessionRequest("/api/email-draft", payload);
    if (draftGeneration === state.draftGeneration) renderDraft(result);
  } catch (error) {
    if (error.stale || draftGeneration !== state.draftGeneration) return;
    $("#form-error").textContent = error.message;
  } finally {
    if (epoch === state.epoch && draftGeneration === state.draftGeneration) submit.disabled = false;
  }
}

async function sendSandboxEmail() {
  if (!state.draft || state.draftDirty || state.revising || state.applyingDraft || !$("#confirm-send").checked) return;
  const sendButton = $("#send-email");
  sendButton.disabled = true;
  sendButton.textContent = "Sandbox 執行中…";
  lockDraftEditor(true);
  $("#send-error").textContent = "";
  try {
    const result = await sessionRequest("/api/email-send", { draft_id: state.draft.draft_id, confirmed: true });
    const receipt = result.receipt;
    $("#draft-status-title").textContent = result.status === "already_processed"
      ? "Sandbox 已處理（未重複寫入）"
      : "Sandbox 執行完成";
    $("#draft-generation-note").textContent = "Write Tool 已回傳執行結果；未寄到真實信箱。";
    $("#tool-trace-note").textContent = `WRITE · send_email · ${result.status}`;
    $("#receipt-status").textContent = result.status;
    $("#receipt-request-id").textContent = receipt.request_id;
    $("#receipt-message-id").textContent = receipt.message_id;
    $("#receipt-time").textContent = receipt.sent_at;
    $("#send-receipt").hidden = false;
    $("#confirmation-panel").hidden = true;
    sendButton.textContent = "已寫入 Sandbox";
    lockDraftEditor(false);
    showToast("Sandbox 執行完成；沒有寄出真實郵件");
  } catch (error) {
    if (error.stale) return;
    $("#send-error").textContent = `${error.payload?.error?.code || "TOOL_FAILED"}：${error.message}`;
    sendButton.disabled = false;
    sendButton.textContent = "重試 Sandbox 執行";
    lockDraftEditor(false);
  }
}

async function copyDraft() {
  if (!$("#draft-body-editor").value) return;
  await navigator.clipboard.writeText(`收件教師：${$("#reuse-teacher").value}\n主旨：${$("#draft-subject-editor").value}\n\n${$("#draft-body-editor").value}`);
  showToast("草稿已複製；系統沒有寄出郵件");
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("show");
  window.setTimeout(() => elements.toast.classList.remove("show"), 2400);
}

async function resetChat() {
  if (!state.session || state.authBusy) return;
  state.draftWorkspaceOpen = false;
  state.epoch += 1;
  state.revising = false;
  state.applyingDraft = false;
  lockDraftEditor(false);
  const epoch = state.epoch;
  state.busy = true;
  state.draft = null;
  state.selectedMemories = [];
  clearTemplateApplication();
  elements.dialog.close();
  elements.draftForm.querySelector('[type="submit"]').disabled = false;
  elements.send.disabled = true;
  $("#new-chat").disabled = true;
  elements.messages.innerHTML = "";
  elements.welcome.hidden = false;
  elements.input.value = "";
  try {
    await sessionRequest("/api/session/reset");
    showToast("已清除本次教師脈絡與待確認草稿；執行紀錄仍保留");
  } catch (error) {
    if (error.stale) return;
    state.session = null;
    showToast(`清除未完成，請重新載入頁面：${error.message}`);
  } finally {
    if (epoch === state.epoch) {
      state.busy = false;
      $("#new-chat").disabled = false;
      elements.send.disabled = !state.session;
      elements.input.focus();
    }
  }
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
$("#edit-draft").addEventListener("click", clearAppliedDraft);
$("#copy-draft").addEventListener("click", copyDraft);
$("#confirm-send").addEventListener("change", (event) => {
  $("#send-email").disabled = !event.currentTarget.checked || state.draftDirty || !state.draft;
});
$("#send-email").addEventListener("click", sendSandboxEmail);
elements.draftForm.addEventListener("submit", submitDraft);
elements.dialog.addEventListener("click", (event) => { if (event.target === elements.dialog) closeDraft(); });
$("#mobile-menu").addEventListener("click", () => $(".sidebar").classList.toggle("open"));
$("#account-login").addEventListener("click", () => { $("#auth-error").textContent = ""; $("#auth-dialog").showModal(); });
$("#auth-close").addEventListener("click", () => { $("#auth-dialog").close(); $("#auth-password").value = ""; });
$("#auth-form").addEventListener("submit", event => {
  event.preventDefault();
  const action = event.submitter?.value || "login";
  const credentials = {username: $("#auth-username").value, password: $("#auth-password").value};
  $$("#auth-form button").forEach(button => { button.disabled = true; });
  changeAccount(action, credentials);
});
$("#account-logout").addEventListener("click", () => changeAccount("logout"));
async function openMemoryManager() {
  if (!state.session?.account) { showToast("請先登入才能引用自己的草稿"); return; }
  editMemory();
  $("#memory-dialog").showModal();
  try { await loadMemories(); } catch (error) { if (!error.stale) $("#memory-error").textContent = error.message; }
}
$("#manage-memory").addEventListener("click", openMemoryManager);
$("#memory-close").addEventListener("click", () => { $("#memory-dialog").close(); });
$("#memory-new").addEventListener("click", () => editMemory());
$("#memory-kind").addEventListener("change", toggleTemplateFields);
$("#preview-template").addEventListener("click", previewTemplateApplication);
$("#confirm-apply").addEventListener("change", () => { $("#apply-template").disabled = !$("#confirm-apply").checked; });
$("#apply-template").addEventListener("click", applyTemplateApplication);
$("#cancel-template").addEventListener("click", () => {
  state.selectedMemories = state.appliedMemories.map(ref => ({...ref}));
  state.templatePreview = null; $("#template-preview").hidden = true; renderMemoryChoices();
  $("#template-applied").textContent = "已取消選取變更，表單未變動。";
});
$("#save-draft-template").addEventListener("click", saveDraftAsTemplate);
$("#update-draft").addEventListener("click", updateEditedDraft);
$("#revise-email").addEventListener("click", reviseDraftWithAI);
["#draft-subject-editor", "#draft-body-editor"].forEach(selector => $(selector).addEventListener("input", markDraftEdited));
$("#reuse-teacher").addEventListener("change", markDraftEdited);
$("#edit-email-content").addEventListener("click", () => { $("#draft-editor").hidden = false; $("#draft-body-editor").focus(); });
$("#memory-form").addEventListener("submit", event => { event.preventDefault(); writeMemory($("#memory-id").value ? "update" : "create"); });
$("#memory-delete").addEventListener("click", () => writeMemory("delete"));

async function initialize() {
  elements.send.disabled = true;
  const data = await request("/api/session");
  updateSession(data.session);
  await loadConfig();
  elements.send.disabled = false;
}
initialize().catch((error) => showToast(`載入設定失敗：${error.message}`));
