// Offline VM tests of actual app.js state transitions. No browser is controlled.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function element() {
  return {
    innerHTML: '', textContent: '', hidden: false, disabled: false, value: '',
    options: [], style: {}, dataset: {}, classList: {add() {}, remove() {}, toggle() {}},
    addEventListener() {}, focus() {}, close() { this.open = false; },
    showModal() { this.open = true; }, remove() {},
    reset() { this.resetCount = (this.resetCount || 0) + 1; },
    insertAdjacentHTML(_where, html) { this.innerHTML += html; },
    querySelector(selector) {
      if (selector === '[type="submit"]') return this.submit ??= element();
      this.fields ??= new Map();
      if (!this.fields.has(selector)) this.fields.set(selector, element());
      return this.fields.get(selector);
    },
  };
}
async function harness() {
  const dom = new Map();
  const get = key => { if (!dom.has(key)) dom.set(key, element()); return dom.get(key); };
  const pending = new Map();
  const session = generation => ({session_id: 'synthetic-session', generation, csrf_token: 'synthetic-csrf', context_teacher: null});
  const response = data => ({ok: true, json: async () => data});
  const sandbox = {
    document: {querySelector: get, querySelectorAll: () => []},
    window: {setTimeout() {}}, requestAnimationFrame: callback => callback(),
    crypto: require('node:crypto').webcrypto,
    FormData: class { entries() { return Object.entries({teacher_name: '林朝興', purpose: 'other', student_name: '合成學生', request_details: '合成詢問測試資料'}); } },
    fetch: async url => {
      if (url === '/api/session') return response({session: session(0)});
      if (url === '/api/config') return response({memory_contract:'private-draft-revision-v3', teachers: [], purposes: [], source: {source_url: 'https://example.invalid'}, email_generation: {configured: false}});
      if (url === '/api/session/reset') return response({session: session(1)});
      return new Promise((resolve, reject) => {
        const complete = data => resolve(response(data));
        complete.fail = reject;
        pending.set(url, complete);
      });
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../ui/app.js'), 'utf8'), sandbox);
  await new Promise(resolve => setImmediate(resolve));
  return {dom, pending, run: code => vm.runInContext(code, sandbox), session};
}

(async () => {
  const chat = await harness();
  const oldChat = chat.run('sendMessage("林朝興老師的研究領域")');
  assert(chat.pending.has('/api/chat'));
  await chat.run('resetChat()');
  chat.pending.get('/api/chat')({status: 'ok', answer: '舊教師答案', detected_teacher: '林朝興', session: {...chat.session(0), context_teacher: '林朝興'}});
  await oldChat;
  assert.equal(chat.run('state.session.generation'), 1);
  assert.equal(chat.run('state.session.context_teacher'), null);
  assert.equal(chat.dom.get('#messages').innerHTML, '');
  assert.equal(chat.run('state.busy'), false);

  const draft = await harness();
  const oldDraft = draft.run('submitDraft({preventDefault() {}})');
  assert(draft.pending.has('/api/email-draft'));
  assert.equal(draft.dom.get('#draft-form').submit.disabled, true);
  await draft.run('resetChat()');
  draft.run('openDraft()');
  assert.equal(draft.dom.get('#draft-form').submit.disabled, false);
  draft.pending.get('/api/email-draft')({status: 'draft_created', draft_id: 'old-draft', session: draft.session(0)});
  await oldDraft;
  assert.equal(draft.run('state.draft'), null);
  assert.equal(draft.run('state.session.generation'), 1);
  assert.equal(draft.dom.get('#draft-form').hidden, false);
  assert.equal(draft.dom.get('#draft-result').hidden, true);
  const account = await harness();
  const login = account.run('changeAccount("login", {username:"synthetic", password:"synthetic-only-password"})');
  account.pending.get('/api/auth/login')({session: {...account.session(0), account: {username:'synthetic'}}});
  await new Promise(resolve => setImmediate(resolve));
  account.pending.get('/api/memory/list')({memories: [{memory_id:'synthetic-memory', version:1, title:'自介', kind:'introduction', content:'合成私人段落'}]});
  await login;
  assert.equal(account.run('state.memories.length'), 1);
  account.run('state.selectedMemories = [{memory_id:"synthetic-memory", version:1}]');
  account.dom.get('#message-input').value = '前帳號尚未送出的私人文字';
  const resetCount = account.dom.get('#draft-form').resetCount;
  const oldAccountChat = account.run('sendMessage("林朝興老師的研究領域")');
  const logout = account.run('changeAccount("logout")');
  assert.equal(account.run('state.memories.length'), 0);
  assert.equal(account.run('state.selectedMemories.length'), 0);
  assert.equal(account.dom.get('#message-input').value, '');
  assert(account.dom.get('#draft-form').resetCount > resetCount);
  account.pending.get('/api/auth/logout')({session: {...account.session(0), account:null}});
  await logout;
  account.pending.get('/api/chat')({status:'ok', answer:'前帳號的舊回答', session:{...account.session(0), account:{username:'synthetic'}}});
  await oldAccountChat;
  assert.equal(account.run('state.session.account'), null);
  assert.equal(account.dom.get('#messages').innerHTML, '');

  const retry = await harness();
  retry.run('updateSession({...state.session, account:{username:"synthetic"}})');
  retry.run('$("#memory-title").value="自介"; $("#memory-kind").value="introduction"; $("#memory-content").value="合成測試文字"; $("#confirm-memory").checked=true;');
  const firstSave = retry.run('writeMemory("create")');
  const operation = retry.run('state.memoryOperation.id');
  retry.pending.get('/api/memory/write').fail(new Error('offline dropped response injection'));
  await firstSave;
  const nextSave = retry.run('writeMemory("create")');
  assert.equal(retry.run('state.memoryOperation.id'), operation);
  retry.pending.get('/api/memory/write')({status:'memory_saved'});
  await new Promise(resolve => setImmediate(resolve));
  retry.pending.get('/api/memory/list')({memories:[]});
  await nextSave;
  assert.equal(retry.run('state.memoryOperation'), null);
  const templates = await harness();
  templates.run(`
    state.config.teachers = [{name:'林朝興'}, {name:'另一位教師'}];
    state.config.purposes = [{value:'other', label:'其他'}, {value:'answer_request', label:'解答詢問'}];
    state.memories = [
      {memory_id:'full', version:1, title:'微積分', kind:'draft_template', content:'老師您好：請問 Practice 3 解答。合成學生 敬上', template_fields:{teacher_name:'林朝興', subject:'Practice 解答詢問'}},
      {memory_id:'text', version:1, title:'自介', kind:'introduction', content:'已選自介'},
      {memory_id:'unselected', version:1, title:'未選', kind:'other', content:'不應出現的文字'}
    ];
    draftField('teacher_name').value = '另一位教師'; draftField('purpose').value = 'other';
    draftField('student_name').value = '本次學生'; draftField('request_details').value = '原本寫的內容';
    state.selectedMemories = [{memory_id:'full',version:1}, {memory_id:'text',version:1}];
    previewTemplateApplication();
  `);
  assert.equal(templates.run('draftField("teacher_name").value'), '另一位教師');
  const previewText = templates.dom.get('#template-preview-text').textContent;
  assert(previewText.includes('主旨：Practice 解答詢問') && previewText.includes('請問 Practice 3 解答'));
  assert(previewText.includes('已選自介'));
  assert(!previewText.includes('不應出現的文字'));
  templates.run('applyTemplateApplication()');
  assert.equal(templates.run('draftField("request_details").value'), '原本寫的內容');
  templates.run('$("#confirm-apply").checked = true; applyTemplateApplication()');
  assert.equal(templates.run('draftField("teacher_name").value'), '另一位教師');
  assert.equal(templates.run('draftField("purpose").value'), 'other');
  assert.equal(templates.dom.get('#reuse-teacher').value, '林朝興');
  assert.equal(templates.dom.get('#draft-subject-editor').value, 'Practice 解答詢問');
  assert(templates.dom.get('#draft-body-editor').value.includes('請問 Practice 3 解答'));
  assert.equal(templates.run('state.draft'), null);
  assert.equal(templates.dom.get('#send-email').disabled, true);
  assert.equal(templates.run('draftField("student_name").value'), '本次學生');
  assert.equal(templates.run('state.appliedMemories.length'), 2);

  templates.run(`
    state.selectedMemories = [{memory_id:'text',version:1}];
    previewTemplateApplication();
    draftField('request_details').value = '預覽之後手動改過';
    $('#confirm-apply').checked = true; applyTemplateApplication();
  `);
  assert(templates.dom.get('#form-error').textContent.includes('重新預覽'));
  assert.equal(templates.run('state.appliedMemories.length'), 2);
  await templates.run('submitDraft({preventDefault() {}})');
  assert(!templates.pending.has('/api/email-draft'));
  assert(templates.dom.get('#form-error').textContent.includes('確認套用'));

  templates.run(`
    state.selectedMemories = [{memory_id:'full',version:1}, {memory_id:'full',version:1}];
    previewTemplateApplication();
  `);
  assert(templates.dom.get('#form-error').textContent.includes('一次只能選一份'));

  const reuse = await harness();
  await reuse.run(`applySavedDraft('mine');`);
  assert(reuse.dom.get('#draft-apply-error').textContent.includes('請先登入'));
  reuse.run(`
    updateSession({...state.session, account:{username:'synthetic'}});
    state.config.teachers=[{name:'林朝興'}];
    state.memories=[{memory_id:'mine',version:1,kind:'draft_template',title:'我的 Practice 詢問',content:'老師您好：\\n請問 Practice 解答。\\n測試學生 敬上',template_fields:{teacher_name:'林朝興',subject:'我的完整信件主旨'}}];
  `);
  const referenced = reuse.run('applySavedDraft("mine")');
  assert(reuse.pending.has('/api/email-template-draft'));
  assert.equal(reuse.dom.get('#send-email').disabled, true);
  reuse.pending.get('/api/email-template-draft')({draft_id:'referenced-draft',teacher:{teacher_name:'林朝興'},email_draft:{to:'official@example.invalid',subject:'我的完整信件主旨',body:'老師您好：請問 Practice 解答。測試學生 敬上'},generation:{provider:'saved_draft'}});
  await referenced;
  assert.equal(reuse.dom.get('#draft-result').hidden, false);
  assert.equal(reuse.dom.get('#draft-form').hidden, true);
  assert.equal(reuse.dom.get('#draft-editor').hidden, true);
  assert(reuse.dom.get('#draft-letter-body').textContent.includes('測試學生 敬上'));
  assert.equal(reuse.dom.get('#send-email').disabled, true);
  assert.equal(reuse.run('state.draft.draft_id'), 'referenced-draft');
  assert.equal(reuse.run('state.draftTemplateId'), 'mine');
  assert.equal(reuse.dom.get('#confirm-send').checked, false);
  reuse.run(`state.memories.push({memory_id:'another',version:1,kind:'draft_template',title:'另一封',content:'另一封正文',template_fields:{teacher_name:'林朝興',subject:'另一封主旨'}});`);
  const failedSwitch = reuse.run('applySavedDraft("another")');
  reuse.pending.get('/api/email-template-draft').fail(new Error('模擬版本已變更'));
  await failedSwitch;
  assert.equal(reuse.run('state.draftTemplateId'), 'mine');
  assert.equal(reuse.run('state.draft.draft_id'), 'referenced-draft');
  assert(reuse.dom.get('#draft-apply-error').textContent.includes('版本已變更'));
  assert.equal((reuse.dom.get('#saved-draft-list').innerHTML.match(/ checked/g) || []).length, 1);
  reuse.run('clearAppliedDraft()');
  assert.equal(reuse.run('state.draftTemplateId'), null);
  assert.equal(reuse.dom.get('#draft-form').hidden, false);
  assert.equal(reuse.dom.get('#draft-result').hidden, true);
  const savedDraft = await harness();
  savedDraft.run(`
    updateSession({...state.session, account:{username:'synthetic'}});
    state.draft = {draft_id:'source-draft', email_draft:{subject:'模型主旨', body:'模型正文'}};
    draftField('request_details').value = '表單內容不應被另存';
    $('#reuse-teacher').value = '林朝興';
    $('#draft-subject-editor').value = '我確認的主旨';
    $('#draft-body-editor').value = '我修改後完整正文：Practice 6。署名甲';
    saveDraftAsTemplate();
  `);
  assert.equal(savedDraft.dom.get('#memory-content').value, '我修改後完整正文：Practice 6。署名甲');
  assert.equal(savedDraft.dom.get('#template-subject').value, '我確認的主旨');
  assert.equal(savedDraft.dom.get('#memory-source-draft').value, 'source-draft');
  assert.equal(savedDraft.dom.get('#confirm-memory').checked, false);
  const html = fs.readFileSync(path.join(__dirname, '../ui/index.html'), 'utf8');
  assert(!html.includes('另存目前表單'));
  assert(!html.includes('公版'));
  assert(html.includes('勾選一份直接套用'));
  assert(!html.includes('confirm-reuse'));
  assert(html.indexOf('id="saved-draft-picker"') < html.indexOf('id="draft-form"'));
  assert(!fs.readFileSync(path.join(__dirname, '../ui/app.js'), 'utf8').includes('data-draft-reuse'));
  assert(html.indexOf('id="save-draft-template"') > html.indexOf('id="draft-result"'));

  const edited = await harness();
  edited.run(`
    renderDraft({draft_id:'before-edit', teacher:{teacher_name:'林朝興'}, email_draft:{to:'official@example.invalid',subject:'舊主旨',body:'舊正文'},generation:{provider:'local_template'}});
    $('#confirm-send').checked=true; $('#draft-body-editor').value='修改後的正文'; markDraftEdited();
  `);
  assert.equal(edited.dom.get('#confirm-send').checked, false);
  assert.equal(edited.dom.get('#send-email').disabled, true);
  await edited.run('sendSandboxEmail()');
  assert(!edited.pending.has('/api/email-send'));
  const editRequest = edited.run('updateEditedDraft()');
  assert(edited.pending.has('/api/email-draft-edit'));
  edited.pending.get('/api/email-draft-edit')({draft_id:'after-edit',teacher:{teacher_name:'林朝興'},email_draft:{to:'official@example.invalid',subject:'舊主旨',body:'修改後的正文'},generation:{provider:'saved_draft'}});
  await editRequest;
  assert.equal(edited.run('state.draft.draft_id'), 'after-edit');
  assert.equal(edited.run('state.draftDirty'), false);
  assert.equal(edited.dom.get('#confirm-send').checked, false);
  const incompatible = await harness();
  incompatible.run(`delete state.config.memory_contract; $('#confirm-memory').checked=true;`);
  await incompatible.run('writeMemory("create")');
  assert(!incompatible.pending.has('/api/memory/write'));
  assert(incompatible.dom.get('#memory-error').textContent.includes('後端仍是舊版本'));
  incompatible.run('saveDraftAsTemplate()');
  assert(incompatible.dom.get('#toast').textContent.includes('Ctrl+C'));
  const revision = await harness();
  revision.run(`
    renderDraft({draft_id:'revision-base', teacher:{teacher_name:'林朝興'}, email_draft:{to:'official@example.invalid',subject:'原主旨',body:'原正文'}, generation:{provider:'saved_draft'}});
    state.memories=[{memory_id:'saved',version:1,kind:'draft_template',content:'保存的原模板'}];
    $('#revision-instructions').value='改成 Practice 4 第 2 題，語氣簡短'; $('#confirm-send').checked=true;
  `);
  const revisionRequest = revision.run('reviseDraftWithAI()');
  assert(revision.pending.has('/api/email-draft-revise'));
  assert.equal(revision.dom.get('#send-email').disabled, true);
  assert.equal(revision.dom.get('#confirm-send').checked, false);
  revision.pending.get('/api/email-draft-revise')({draft_id:'revision-new', teacher:{teacher_name:'林朝興'}, email_draft:{to:'official@example.invalid',subject:'Practice 4',body:'調整後的正文'},generation:{provider:'gemini',model:'offline-vm-spy'}});
  await revisionRequest;
  assert.equal(revision.run('state.draft.draft_id'), 'revision-new');
  assert.equal(revision.run('state.memories[0].content'), '保存的原模板');
  assert.equal(revision.dom.get('#draft-letter-body').textContent, '調整後的正文');
  assert.equal(revision.dom.get('#confirm-send').checked, false);
  assert.equal(revision.run('state.revising'), false);

  const failureRevision = revision.run('reviseDraftWithAI()');
  const providerFailure = new Error('模擬模型服務失敗，原草稿保留');
  providerFailure.payload = {generation:{evidence_status:'LIVE_FAIL'}};
  revision.pending.get('/api/email-draft-revise').fail(providerFailure);
  await failureRevision;
  assert.equal(revision.run('state.draft.draft_id'), 'revision-new');
  assert.equal(revision.dom.get('#draft-letter-body').textContent, '調整後的正文');
  assert(revision.dom.get('#revision-status').textContent.includes('LIVE_FAIL'));
  revision.run('$("#confirm-send").checked=true');
  const sentRevision = revision.run('sendSandboxEmail()');
  revision.pending.get('/api/email-send')({status:'sent', receipt:{request_id:'synthetic-request',message_id:'synthetic-message',sent_at:'synthetic-time'}});
  await sentRevision;
  assert.equal(revision.dom.get('#nav-email').disabled, false);
  assert.equal(revision.dom.get('#revise-email').disabled, false);

  revision.run(`$('#draft-body-editor').value='手動改好的正文'; markDraftEdited();`);
  const dirtyRevision = revision.run('reviseDraftWithAI()');
  assert(revision.pending.has('/api/email-draft-edit'));
  revision.pending.get('/api/email-draft-edit')({draft_id:'manual-new', teacher:{teacher_name:'林朝興'}, email_draft:{to:'official@example.invalid',subject:'Practice 4',body:'手動改好的正文'},generation:{provider:'saved_draft'}});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(revision.run('state.draft.draft_id'), 'manual-new');
  assert.equal(revision.run('state.revising'), true);
  revision.pending.get('/api/email-draft-revise')({draft_id:'manual-then-ai', teacher:{teacher_name:'林朝興'}, email_draft:{to:'official@example.invalid',subject:'Practice 4',body:'以手動修改為基礎的 AI 正文'},generation:{provider:'gemini',model:'offline-vm-spy'}});
  await dirtyRevision;
  assert.equal(revision.run('state.draft.draft_id'), 'manual-then-ai');

  const lateRevision = revision.run('reviseDraftWithAI()');
  await revision.run('resetChat()');
  revision.pending.get('/api/email-draft-revise')({draft_id:'must-discard', teacher:{teacher_name:'林朝興'}, email_draft:{to:'official@example.invalid',subject:'過期結果',body:'過期正文'},generation:{provider:'gemini',model:'offline-vm-spy'}});
  await lateRevision;
  assert.equal(revision.run('state.draft'), null);
  assert.equal(revision.run('state.revising'), false);
  assert.notEqual(revision.dom.get('#draft-letter-body').textContent, '過期正文');
  assert.equal(revision.dom.get('#nav-email').disabled, false);
  const serviceError = await harness();
  serviceError.run(`
    renderDraft({draft_id:'preserved-original', teacher:{teacher_name:'林朝興'}, email_draft:{to:'official@example.invalid',subject:'原主旨',body:'原正文及署名'},generation:{provider:'saved_draft'}});
    elements.dialog.showModal(); $('#revision-instructions').value='語氣簡短禮貌';
    fetch = async () => ({ok:false, json:async()=>({status:'revision_unavailable',reason:'尚未設定 Gemini，原草稿已保留。',error:{code:'MODEL_NOT_CONFIGURED'},generation:{evidence_status:'LIVE_NOT_RUN'},session:{...state.session}})});
  `);
  await serviceError.run('reviseDraftWithAI()');
  assert.equal(serviceError.run('state.draft.draft_id'), 'preserved-original');
  assert.equal(serviceError.dom.get('#draft-dialog').open, true);
  assert.equal(serviceError.dom.get('#draft-letter-body').textContent, '原正文及署名');
  assert(serviceError.dom.get('#revision-status').textContent.includes('LIVE_NOT_RUN'));
  assert.equal(serviceError.dom.get('#confirm-send').checked, false);
  assert.equal(serviceError.dom.get('#confirm-send').disabled, false);
  assert.equal(serviceError.dom.get('#revise-email').disabled, false);
  serviceError.run(`fetch = async () => ({ok:false, json:async()=>({status:'revision_failed',reason:'模型服務失敗，原草稿已保留。',error:{code:'MODEL_REVISION_FAILED'},generation:{evidence_status:'LIVE_FAIL',failure_reason:'Gemini HTTP 429: synthetic-provider-detail'},session:{...state.session}})});`);
  await serviceError.run('reviseDraftWithAI()');
  assert.equal(serviceError.run('state.draft.draft_id'), 'preserved-original');
  assert.equal(serviceError.dom.get('#draft-dialog').open, true);
  assert(serviceError.dom.get('#revision-status').textContent.includes('LIVE_FAIL'));
  assert(serviceError.dom.get('#revision-status').textContent.includes('Gemini HTTP 429'));
  assert(serviceError.dom.get('#revision-status').textContent.includes('synthetic-provider-detail'));
  serviceError.run(`fetch = async () => ({ok:false, json:async()=>({reason:'AI 調整失敗，原草稿已保留。',error:{code:'MODEL_REVISION_FAILED'},generation:{evidence_status:'LIVE_FAIL',failure_reason:'functionCall stage: Gemini HTTP 503: The model is overloaded. api_key=synthetic-secret Bearer synthetic-token AIzaSyntheticKey123'},session:{...state.session}})});`);
  await serviceError.run('reviseDraftWithAI()');
  const failureText = serviceError.dom.get('#revision-status').textContent;
  assert(failureText.includes('Gemini HTTP 503: The model is overloaded.'));
  assert(!failureText.includes('synthetic-secret'));
  assert(!failureText.includes('synthetic-token'));
  assert(!failureText.includes('AIzaSyntheticKey123'));
  assert.equal(serviceError.run('state.draft.draft_id'), 'preserved-original');
  assert.equal(serviceError.dom.get('#draft-dialog').open, true);
  assert.equal(serviceError.dom.get('#revision-instructions').value, '語氣簡短禮貌');
  serviceError.run(`fetch = async () => ({ok:false, json:async()=>({reason:'模型離線驗收中的對話失效',error:{code:'STALE_SESSION'},session:{...state.session,generation:state.session.generation+1}})});`);
  await serviceError.run('reviseDraftWithAI()');
  assert.equal(serviceError.run('state.draft'), null);
  assert.equal(serviceError.dom.get('#draft-dialog').open, true);
  assert.equal(serviceError.dom.get('#draft-letter-body').textContent, '原正文及署名');
  assert.equal(serviceError.dom.get('#send-email').disabled, true);
  assert.equal(serviceError.run('state.session.generation'), 1);
  const resume = await harness();
  await resume.run('openDraft()');
  resume.run(`draftField('request_details').value='尚未產生的詢問'; state.selectedMemories=[{memory_id:'selected',version:1}]; closeDraft();`);
  await resume.run('openDraft("另一位教師", "other")');
  assert.equal(resume.run("draftField('request_details').value"), '尚未產生的詢問');
  assert.equal(resume.run('state.selectedMemories.length'), 1);
  resume.run(`renderDraft({draft_id:'resume-draft',teacher:{teacher_name:'林朝興'},email_draft:{to:'official@example.invalid',subject:'原主旨',body:'原正文'},generation:{provider:'saved_draft'}});
    $('#draft-editor').hidden=false; $('#draft-body-editor').value='尚未確認的修改'; markDraftEdited();
    $('#revision-instructions').value='保留原署名'; closeDraft();`);
  await resume.run('openDraft()');
  assert.equal(resume.run('state.draft.draft_id'), 'resume-draft');
  assert.equal(resume.run('state.draftDirty'), true);
  assert.equal(resume.dom.get('#draft-body-editor').value, '尚未確認的修改');
  assert.equal(resume.dom.get('#revision-instructions').value, '保留原署名');
  assert.equal(resume.dom.get('#draft-editor').hidden, false);
  assert.equal(resume.dom.get('#draft-result').hidden, false);
  assert.equal(resume.dom.get('#send-email').disabled, true);
  await resume.run('resetChat()');
  await resume.run('openDraft()');
  assert.equal(resume.run('state.draft'), null);
  assert.equal(resume.dom.get('#draft-result').hidden, true);
  assert.equal(resume.dom.get('#revision-instructions').value, '');

  const pendingResume = await harness();
  await pendingResume.run('openDraft()');
  const pendingCreation = pendingResume.run('submitDraft({preventDefault(){}})');
  pendingResume.run('closeDraft()');
  await pendingResume.run('openDraft()');
  assert.equal(pendingResume.dom.get('#draft-form').submit.disabled, true);
  pendingResume.pending.get('/api/email-draft')({draft_id:'finished-while-hidden',teacher:{teacher_name:'林朝興'},email_draft:{to:'official@example.invalid',subject:'完成主旨',body:'完成正文'},generation:{provider:'gemini',model:'offline-spy'}});
  await pendingCreation;
  pendingResume.run('closeDraft()');
  await pendingResume.run('openDraft()');
  assert.equal(pendingResume.run('state.draft.draft_id'), 'finished-while-hidden');
  assert.equal(pendingResume.dom.get('#draft-body-editor').value, '完成正文');
  assert.equal(pendingResume.dom.get('#confirm-send').checked, false);
  pendingResume.run('clearPrivateUI()');
  assert.equal(pendingResume.run('state.draftWorkspaceOpen'), false);
  assert.equal(pendingResume.dom.get('#draft-body-editor').value, '');
  const personal = await harness();
  const facts = [{candidate_id:'synthetic-fact',title:'我的微積分老師',content:'另一位教師',previous_content:'林朝興'}];
  personal.run(`globalThis.personalFacts=${JSON.stringify(facts)}`);
  assert.equal(personal.run('personalMemoryChoices(personalFacts,"test")'), '');
  await personal.run('saveChatMemories(personalFacts,"test")');
  assert(!personal.pending.has('/api/personal-memory/save'));
  personal.run('updateSession({...state.session,account:{username:"synthetic"}})');
  const card = personal.run('personalMemoryChoices(personalFacts,"test")');
  assert(card.includes('原記憶：林朝興'));
  assert(card.includes('覆蓋為：另一位教師'));
  await personal.run('saveChatMemories(personalFacts,"test")');
  assert(personal.dom.get('#personal-status-test').textContent.includes('請先勾選'));
  personal.dom.get('#personal-candidate-synthetic-fact').checked = true;
  const saveFact = personal.run('saveChatMemories(personalFacts,"test")');
  assert(personal.pending.has('/api/personal-memory/save'));
  assert.equal(personal.dom.get('#personal-save-test').disabled, true);
  personal.pending.get('/api/personal-memory/save')({status:'memory_saved',memory_id:'stored-fact',version:2});
  await saveFact;
  assert.equal(personal.dom.get('#personal-candidate-synthetic-fact').disabled, true);
  assert(personal.dom.get('#personal-status-test').textContent.includes('1 筆'));

  const retryFact = [{candidate_id:'retry-fact',title:'我的系所',content:'合成系所',previous_content:null}];
  personal.run(`globalThis.retryFacts=${JSON.stringify(retryFact)}`);
  personal.run('$("#personal-candidate-retry-fact").checked = true');
  const failedFact = personal.run('saveChatMemories(retryFacts,"retry")');
  personal.pending.get('/api/personal-memory/save').fail(new Error('synthetic dropped response'));
  await failedFact;
  const factOperation = personal.run('retryFacts[0].operation_id');
  assert.equal(personal.dom.get('#personal-candidate-retry-fact').disabled, false);
  const repeatFact = personal.run('saveChatMemories(retryFacts,"retry")');
  assert.equal(personal.run('retryFacts[0].operation_id'), factOperation);
  personal.pending.get('/api/personal-memory/save')({status:'memory_saved',idempotent_replay:true});
  await repeatFact;
  assert(personal.dom.get('#personal-status-retry').textContent.includes('1 筆'));
  assert(personal.run('personalMemoryTrace({backend:"gemini",live_status:"LIVE_NOT_RUN",status:"offline_model_double"})').includes('Gemini 語意判斷'));
  assert.equal(personal.run('personalMemoryTrace({status:"guest_disabled"})'), '');
  const fallbackTrace = personal.run('personalMemoryTrace({backend:"rules",live_status:"LIVE_FAIL",status:"semantic_failed_fallback",failure_reason:"Gemini HTTP 503 api_key=synthetic-secret"})');
  assert(fallbackTrace.includes('基本比對'));
  assert(fallbackTrace.includes('Gemini HTTP 503'));
  assert(!fallbackTrace.includes('synthetic-secret'));
  personal.run('personalFacts[0].evidence_quote="<script>合成引文</script>"');
  const quotedCard = personal.run('personalMemoryChoices(personalFacts,"test")');
  assert(quotedCard.includes('&lt;script&gt;'));
  assert(!quotedCard.includes('<script>'));
  const switched = await harness();
  switched.run(`updateSession({...state.session,account:{username:'synthetic'}});
    state.memories=[{memory_id:'new-template',version:1,kind:'draft_template',title:'新的信件',content:'新的正文',template_fields:{teacher_name:'林朝興',subject:'新的主旨'}}];`);
  const initialGeneration = switched.run('submitDraft({preventDefault(){}})');
  const switchOperation = switched.run('applySavedDraft("new-template")');
  switched.pending.get('/api/email-template-draft')({draft_id:'new-selected-draft',teacher:{teacher_name:'林朝興'},email_draft:{to:'official@example.invalid',subject:'新的主旨',body:'新的正文'},generation:{provider:'saved_draft'}});
  await switchOperation;
  switched.pending.get('/api/email-draft')({draft_id:'late-original-draft',teacher:{teacher_name:'林朝興'},email_draft:{to:'official@example.invalid',subject:'過時主旨',body:'過時正文'},generation:{provider:'gemini',model:'offline'}});
  await initialGeneration;
  assert.equal(switched.run('state.draft.draft_id'), 'new-selected-draft');
  assert.equal(switched.dom.get('#draft-body-editor').value, '新的正文');
  console.log(JSON.stringify({mode: 'OFFLINE_JS_VM', tests: 22, status: 'PASS', browser_visual_verified: false}));
})().catch(error => { console.error(error); process.exitCode = 1; });
