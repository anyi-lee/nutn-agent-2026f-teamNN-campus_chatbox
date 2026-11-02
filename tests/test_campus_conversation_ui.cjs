// Deterministic VM tests; no Gemini call and no browser automation.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function element() {
  return {
    innerHTML:'', textContent:'', hidden:false, disabled:false, value:'', checked:false,
    options:[], dataset:{}, style:{}, classList:{add(){}, remove(){}, toggle(){}},
    listeners:{}, addEventListener(name, callback){ this.listeners[name]=callback; },
    focus(){}, remove(){}, reset(){}, close(){this.open=false;}, showModal(){this.open=true;},
    requestSubmit(){ this.submitCount=(this.submitCount||0)+1; },
    insertAdjacentHTML(_where, html){ this.innerHTML += html; },
    querySelector(selector){
      if(selector==='[type="submit"]') return this.submit ??= element();
      this.fields ??= new Map();
      if(!this.fields.has(selector)) this.fields.set(selector,element());
      return this.fields.get(selector);
    }
  };
}
async function harness() {
  const dom = new Map(), calls = [], pending = [];
  const get = key => { if (!dom.has(key)) dom.set(key, element()); return dom.get(key); };
  const session = generation => ({session_id:'synthetic-session', generation, csrf_token:'synthetic-csrf'});
  const response = data => ({ok:true, json:async()=>data});
  const sandbox = {
    document:{querySelector:get, querySelectorAll:()=>[]}, window:{setTimeout(){}},
    requestAnimationFrame:fn=>fn(), crypto:require('node:crypto').webcrypto,
    FormData:class { entries(){ return Object.entries({
      teacher_name:get('#teacher-name').value, recipient_mode:get('#recipient-office').checked?'office':'academic',
      ...Object.fromEntries(['purpose','student_name','student_department','student_grade','request_details','background'].map(key=>[key,key==='purpose'?get('#purpose').value:get('#draft-form').querySelector(`[name="${key}"]`).value]))
    }); } },
    fetch:async(url, options={})=>{
      if(url === '/api/session') return response({session:session(0)});
      if(url === '/api/config') return response({memory_contract:'private-draft-revision-v3',teachers:JSON.parse(fs.readFileSync(path.join(__dirname,'../ui/email_directory.json'),'utf8')).recipients.map(row=>({name:row.name,title:row.title})),purposes:[{value:'other',label:'其他'}],source:{},email_generation:{configured:false}});
      if(url.startsWith('/email_directory.json')) return response(JSON.parse(fs.readFileSync(path.join(__dirname,'../ui/email_directory.json'),'utf8')));
      if(url === '/api/session/reset') return response({session:session(1)});
      calls.push({url, payload:JSON.parse(options.body)});
      return new Promise((resolve,reject)=>pending.push({resolve:data=>resolve(response(data)),reject}));
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../ui/app.js'),'utf8'),sandbox);
  await new Promise(resolve=>setImmediate(resolve));
  ['#email-message','#confirm-send'].forEach(get);
  get('#email-dialogue').innerHTML='<p>這封信想寫給誰？例如林朝興老師。</p>';
  return {dom,calls,pending,session,get,run:code=>vm.runInContext(code,sandbox)};
}

(async()=>{
  const retry = await harness();
  retry.dom.get('#email-message').value='想寫信給國文系';
  const first = retry.run('sendEmailConversation()');
  assert.equal(retry.dom.get('#email-message').value,'','email input clears before response');
  assert.equal(retry.calls[0].url,'/api/email-conversation');
  assert.equal(retry.dom.get('#email-conversation-send').disabled,true);
  await retry.run('sendEmailConversation()');
  assert.equal(retry.calls.length,1,'double click suppressed');
  retry.pending[0].reject(new Error('synthetic network failure'));
  await first;
  assert.equal(retry.dom.get('#email-message').value,'想寫信給國文系');
  const second = retry.run('sendEmailConversation()');
  assert.equal(retry.calls[1].payload.turn_id,retry.calls[0].payload.turn_id,'retry uses same turn id');
  retry.pending[1].resolve({answer:'想詢問什麼？',analysis:{backend:'rules'},session:retry.session(0)});
  await second;
  assert.equal(retry.dom.get('#email-message').value,'');
  assert.equal(retry.run('state.emailPendingTurn'),null);
  assert.equal((retry.dom.get('#email-dialogue').innerHTML.match(/email-turn user/g)||[]).length,1);

  const complete = await harness();
  complete.dom.get('#email-message').value='我叫合成學生';
  complete.dom.get('#confirm-send').checked=true;
  const job = complete.run('sendEmailConversation()');
  const draft = {draft_id:'synthetic-draft',teacher:{teacher_name:'國語文學系'},generation:{provider:'local_template'},
    email_draft:{to:'synthetic@example.invalid',subject:'合成主旨',body:'合成正文'},answer:'請檢查草稿',session:complete.session(0)};
  complete.pending[0].resolve(draft);
  await job;
  assert.equal(complete.run('state.draft.draft_id'),'synthetic-draft');
  assert.equal(complete.dom.get('#email-conversation').hidden,true);
  assert.equal(complete.dom.get('#draft-result').hidden,false);
  assert.equal(complete.dom.get('#confirm-send').checked,false);
  assert.equal(complete.dom.get('#send-email').disabled,true);
  assert(!complete.calls.some(call=>call.url==='/api/email-send'),'never sends from collection');

  const stale = await harness();
  stale.dom.get('#email-message').value='舊的私人內容';
  const old = stale.run('sendEmailConversation()');
  await stale.run('resetChat()');
  stale.pending[0].resolve({...draft,session:stale.session(0)});
  await old;
  assert.equal(stale.run('state.draft'),null);
  assert.equal(stale.dom.get('#email-dialogue').innerHTML,'');
  assert.equal(stale.run('state.session.generation'),1);
  assert.equal(stale.dom.get('#email-conversation-send').disabled,false);

  const chat = await harness();
  chat.dom.get('#message-input').value='找國文系';
  const chatJob = chat.run('sendMessage(elements.input.value)');
  assert.equal(chat.dom.get('#message-input').value,'','main input clears before response');
  chat.pending[0].reject(new Error('synthetic network failure'));
  await chatJob;
  assert.equal(chat.dom.get('#message-input').value,'找國文系','failed message is restored');
  const nextChat = chat.run('sendMessage(elements.input.value)');
  chat.dom.get('#message-input').value='下一個尚未送出的問題';
  chat.pending[1].resolve({status:'ok',answer:'官方單位入口',session:chat.session(0)});
  await nextChat;
  assert.equal(chat.dom.get('#message-input').value,'下一個尚未送出的問題');

  const typing = await harness();
  typing.dom.get('#email-message').value='第一則訊息';
  const typingJob = typing.run('sendEmailConversation()');
  typing.dom.get('#email-message').value='還在輸入的新文字';
  typing.pending[0].resolve({answer:'請補充對象',session:typing.session(0)});
  await typingJob;
  assert.equal(typing.dom.get('#email-message').value,'還在輸入的新文字');
  const failedJob = typing.run('sendEmailConversation()');
  typing.dom.get('#email-message').value='新的草稿文字';
  typing.pending[1].reject(new Error('synthetic failure'));
  await failedJob;
  assert.equal(typing.dom.get('#email-message').value,'新的草稿文字','failure must not overwrite newer typing');

  const ime = await harness();
  const field = ime.dom.get('#message-input'), form = ime.dom.get('#chat-form');
  const enter = extra=>({key:'Enter',shiftKey:false,preventDefault(){this.prevented=true;},...extra});
  field.listeners.keydown(enter({isComposing:true}));
  field.listeners.keydown(enter({keyCode:229}));
  field.listeners.compositionstart();
  field.listeners.keydown(enter({}));
  assert.equal(form.submitCount,undefined,'IME confirmation never submits');
  field.listeners.compositionend();
  field.listeners.keydown(enter({shiftKey:true}));
  assert.equal(form.submitCount,undefined,'Shift+Enter stays newline');
  field.listeners.keydown(enter({}));
  assert.equal(form.submitCount,1,'plain Enter submits after composition ends');

  const answer = await harness();
  answer.run('state.config.teachers=[{name:"陳榮銘"},{name:"國語文學系"}]');
  assert.equal(answer.run('emailRecipientsForAnswer({status:"ok",detected_teacher:"陳榮銘",suggested_action:null}).join()'),'陳榮銘');
  assert.equal(answer.run('emailRecipientsForAnswer({status:"ok",evidence:{units:[{name:"國語文學系",public_email:"synthetic@example.invalid"}]}}).join()'),'國語文學系');
  assert.equal(answer.run('emailRecipientsForAnswer({status:"ok",detected_teacher:"未收錄對象"}).length'),0);
  assert.equal(answer.run('emailRecipientsForAnswer({status:"insufficient_evidence",detected_teacher:"陳榮銘"}).length'),0);
  answer.run('addAssistantMessage({status:"ok",answer:"依你的記憶找到陳榮銘",detected_teacher:"陳榮銘",suggested_action:null})');
  assert.match(answer.dom.get('#messages').innerHTML,/寫信給陳榮銘/);
  const action = [...answer.dom.entries()].find(([key])=>key.includes('[data-email-action="0"]'))[1];
  action.listeners.click();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(answer.run('state.emailRecipientHint'),'陳榮銘');
  assert.match(answer.dom.get('#email-dialogue').innerHTML,/這封信要寫給陳榮銘/);
  assert.doesNotMatch(answer.dom.get('#email-dialogue').innerHTML,/林朝興/,'static example is replaced by actual recipient');
  assert.equal(answer.calls.length,0,'opening an email does not call a model or send mail');

  answer.run('state.emailHasTurns=true');
  await answer.run('openDraftForRecipient("國語文學系")');
  assert.equal(answer.dom.get('#email-switch-prompt').hidden,false);
  assert.equal(answer.run('state.emailRecipientHint'),'陳榮銘','recipient never silently changes mid-draft');
  answer.dom.get('#email-switch-cancel').listeners.click();
  assert.equal(answer.dom.get('#email-switch-prompt').hidden,true);

  async function pendingSend() {
    const flow = await harness();
    await flow.run('openDraft()');
    flow.run(`selectRecipientByName('林朝興'); $('#purpose').value='other';
      draftField('student_name').value='合成學生'; draftField('student_department').value='測試系所';
      draftField('student_grade').value='大四'; draftField('request_details').value='合成詢問內容';
      draftField('background').value='合成補充背景';
      state.selectedMemories=[{memory_id:'synthetic-snippet',version:1}];
      state.appliedMemories=[{memory_id:'synthetic-snippet',version:1}];
      state.emailFormDirty=true; $('#saved-draft-picker').open=true;
      renderDraft({draft_id:'sent-reset-draft',teacher:{teacher_name:'林朝興'},
        email_draft:{to:'synthetic@example.invalid',subject:'合成主旨',body:'合成正文'},
        generation:{provider:'local_template'}});
      $('#confirm-send').checked=true;`);
    const send = flow.run('sendSandboxEmail()');
    return {flow,send};
  }
  const receipt = {request_id:'synthetic-request',message_id:'synthetic-message',sent_at:'synthetic-time'};
  for (const status of ['simulated_sent','already_processed']) {
    const {flow,send} = await pendingSend();
    await flow.run('sendSandboxEmail()');
    assert.equal(flow.calls.length,1,'duplicate send is blocked while pending');
    flow.pending[0].resolve({status,receipt,session:flow.session(0)});
    await send;
    assert.equal(flow.run('state.completedDraftId'),'sent-reset-draft');
    assert.equal(flow.get('#send-receipt').hidden,false,'receipt remains visible before reopening');
    await flow.run('sendSandboxEmail()');
    assert.equal(flow.calls.length,1,'successful draft cannot be sent again');
    flow.run('closeDraft()');
    await flow.run('openDraft()');
    assert.equal(flow.get('#draft-form').hidden,false);
    assert.equal(flow.get('#draft-result').hidden,true);
    assert.equal(flow.get('#recipient-office').checked,true);
    for (const key of ['student_name','student_department','student_grade','request_details','background']) {
      assert.equal(flow.run(`draftField(${JSON.stringify(key)}).value`),'',`${status}: ${key} clears`);
    }
    for (const selector of ['#purpose','#teacher-name','#office-select','#office-section-select','#department-select','#academic-teacher-select','#draft-subject-editor','#draft-body-editor','#revision-instructions']) {
      assert.equal(flow.get(selector).value,'',`${status}: ${selector} clears`);
    }
    assert.equal(flow.run('state.draft'),null);
    assert.equal(flow.run('state.draftDirty'),false);
    assert.equal(flow.run('state.completedDraftId'),null);
    assert.equal(flow.run('state.selectedMemories.length'),0);
    assert.equal(flow.run('state.appliedMemories.length'),0);
    assert.equal(flow.get('#saved-draft-picker').open,false);
    assert.equal(flow.get('#send-receipt').hidden,true);
    assert.equal(flow.get('#receipt-message-id').textContent,'');
    assert.equal(flow.get('#confirm-send').checked,false);
    assert.equal(flow.get('#confirm-send').disabled,true);
    assert.equal(flow.get('#send-email').disabled,true);
    assert.equal(flow.calls.length,1,'reopening neither deletes saved content nor writes a new email');
  }
  const direct = await pendingSend();
  direct.flow.pending[0].resolve({status:'simulated_sent',receipt,session:direct.flow.session(0)});
  await direct.send;
  direct.flow.run('closeDraft()');
  await direct.flow.run('openDraftForRecipient("盧陽明", "other")');
  assert.equal(direct.flow.get('#email-switch-prompt').hidden,true,'finished email does not cause stale recipient-switch prompt');
  assert.equal(direct.flow.get('#teacher-name').value,'盧陽明');
  assert.equal(direct.flow.get('#department-select').value,'電機工程學系');
  assert.equal(direct.flow.run('draftField("student_name").value'),'');
  assert.equal(direct.flow.get('#draft-result').hidden,true);

  const failedSend = await pendingSend();
  failedSend.flow.pending[0].reject(new Error('synthetic write failure'));
  await failedSend.send;
  failedSend.flow.run('closeDraft()');
  await failedSend.flow.run('openDraft()');
  assert.equal(failedSend.flow.run('state.draft.draft_id'),'sent-reset-draft');
  assert.equal(failedSend.flow.run('state.completedDraftId'),null);
  assert.equal(failedSend.flow.get('#draft-body-editor').value,'合成正文');
  assert.equal(failedSend.flow.run('draftField("student_name").value'),'合成學生');
  assert.equal(failedSend.flow.get('#draft-result').hidden,false);
  assert.equal(failedSend.flow.get('#send-receipt').hidden,true);
  assert.equal(failedSend.flow.get('#confirm-send').checked,false);

  const resetSend = await pendingSend();
  await resetSend.flow.run('resetChat()');
  resetSend.flow.pending[0].resolve({status:'simulated_sent',receipt,session:resetSend.flow.session(0)});
  await resetSend.send;
  await resetSend.flow.run('openDraft()');
  assert.equal(resetSend.flow.run('state.draft'),null,'old send completion cannot restore a reset workspace');
  assert.equal(resetSend.flow.run('state.completedDraftId'),null);
  assert.equal(resetSend.flow.get('#draft-result').hidden,true);

  const formFlow = await harness();
  assert.equal(formFlow.run('$("#recipient-office").checked'),true);
  assert.equal(formFlow.get('#academic-picker').hidden,true);
  formFlow.run('setRecipientMode("academic"); $("#department-select").value="資訊工程學系"; updateDepartmentTeachers()');
  assert.match(formFlow.get('#academic-teacher-select').innerHTML,/林朝興/);
  assert.doesNotMatch(formFlow.get('#academic-teacher-select').innerHTML,/盧陽明/);
  formFlow.run('$("#academic-teacher-select").value="林朝興"; updateAcademicRecipient()');
  assert.equal(formFlow.run('validRecipientSelection()'),true);
  formFlow.run('$("#department-select").value="電機工程學系"; updateDepartmentTeachers()');
  assert.equal(formFlow.get('#teacher-name').value,'','changing department clears previous teacher');
  assert.doesNotMatch(formFlow.get('#academic-teacher-select').innerHTML,/林朝興/);
  assert.match(formFlow.get('#academic-teacher-select').innerHTML,/盧陽明/);
  assert.equal(formFlow.run('validRecipientSelection()'),false);
  formFlow.run('$("#academic-teacher-select").value="林朝興"; updateAcademicRecipient()');
  assert.equal(formFlow.run('validRecipientSelection()'),false,'teacher from another department is rejected');
  formFlow.run('$("#department-select").value="應用數學系"; updateDepartmentTeachers()');
  assert.match(formFlow.get('#academic-teacher-select').innerHTML,/黃印良/,'new verified math teachers are available');
  formFlow.run('state.emailDirectory.recipients = state.emailDirectory.recipients.filter(row => row.department !== "應用數學系"); updateDepartmentTeachers()');
  assert.equal(formFlow.get('#academic-teacher-select').disabled,true);
  assert.equal(formFlow.run('validRecipientSelection()'),false,'synthetically unavailable department cannot borrow a teacher');

  const directory = JSON.parse(fs.readFileSync(path.join(__dirname,'../ui/email_directory.json'),'utf8'));
  const office = directory.recipients.find(row=>row.kind==='unit' && directory.units.some(unit=>unit.category==='administrative' && unit.name===row.name));
  formFlow.run(`selectRecipientByName(${JSON.stringify(office.name)})`);
  assert.equal(formFlow.get('#recipient-office').checked,true);
  assert.equal(formFlow.get('#office-select').value,office.name);
  assert.equal(formFlow.run('validRecipientSelection()'),true);
  const noEmail = directory.units.find(unit=>unit.category==='administrative' && !directory.recipients.some(row=>row.name===unit.name));
  formFlow.run(`$('#office-select').value=${JSON.stringify(noEmail.parent_office)}; updateOfficeSections(); $('#office-section-select').value=${JSON.stringify(noEmail.name)}; updateOfficeRecipient()`);
  assert.equal(formFlow.get('#teacher-name').value,'');
  assert.match(formFlow.get('#recipient-note').textContent,/尚未收錄/);
  assert.equal(formFlow.run('validRecipientSelection()'),false);

  const officeFlow = await harness();
  assert.match(officeFlow.get('#office-select').innerHTML,/>教務處</);
  assert.doesNotMatch(officeFlow.get('#office-select').innerHTML,/教務處學籍成績組/,'first list contains only offices');
  assert.equal(officeFlow.get('#office-section-select').disabled,true);
  officeFlow.run('$("#office-select").value="教務處"; updateOfficeSections()');
  assert.match(officeFlow.get('#office-section-select').innerHTML,/學籍成績組/);
  assert.doesNotMatch(officeFlow.get('#office-section-select').innerHTML,/讀者服務組/);
  assert.equal(officeFlow.run('validRecipientSelection()'),false,'choosing office alone is not a recipient');
  officeFlow.run('$("#office-section-select").value="教務處學籍成績組"; updateOfficeRecipient()');
  assert.equal(officeFlow.run('validRecipientSelection()'),false,'unknown section address never falls back to office');
  assert.match(officeFlow.get('#recipient-note').textContent,/不會改寄/);
  officeFlow.run(`state.config.teachers.push({name:'教務處學籍成績組'});
    state.emailDirectory.recipients.push({name:'教務處學籍成績組',department:'教務處學籍成績組',kind:'unit',title:'合成測試窗口'});
    updateOfficeRecipient();`);
  assert.equal(officeFlow.run('validRecipientSelection()'),true,'synthetic fixture verifies a section-level recipient');
  officeFlow.run('$("#office-select").value="圖資處"; updateOfficeSections()');
  assert.equal(officeFlow.get('#office-section-select').value,'');
  assert.equal(officeFlow.get('#teacher-name').value,'');
  officeFlow.run('$("#office-section-select").value="教務處學籍成績組"; updateOfficeRecipient()');
  assert.equal(officeFlow.run('validRecipientSelection()'),false,'another office section is rejected');
  officeFlow.run('selectRecipientByName("教務處學籍成績組")');
  assert.equal(officeFlow.get('#office-select').value,'教務處');
  assert.equal(officeFlow.get('#office-section-select').value,'教務處學籍成績組');
  assert.equal(officeFlow.run('validRecipientSelection()'),true,'answer handoff selects both levels');

  const chinese = await harness();
  chinese.run('setRecipientMode("academic"); $("#department-select").value="國語文學系"; updateDepartmentTeachers()');
  for (const name of ['鄭憲仁','蔡玲婉','林登順','張惠貞','王建國','王琅','陳光明','楊素姿','莊千慧','陳昭吟']) {
    assert(chinese.get('#academic-teacher-select').innerHTML.includes(name));
  }
  assert.doesNotMatch(chinese.get('#academic-teacher-select').innerHTML,/盧陽明/);
  chinese.run('$("#academic-teacher-select").value="鄭憲仁"; updateAcademicRecipient()');
  assert.equal(chinese.get('#teacher-name').value,'鄭憲仁');
  assert.equal(chinese.run('validRecipientSelection()'),true);

  const expanded = await harness();
  const counts = {'教育學系':20,'特殊教育學系':8,'幼兒教育學系':8,'體育學系':9,
    '諮商與輔導學系':9,'文化與自然資源學系':7,'英語學系':6,'應用數學系':8,
    '數位學習科技學系':11,'智慧製造在職學位學程':11,'綠色能源科技學系':8,
    '音樂學系':9,'視覺藝術與設計學系':10,'戲劇創作與應用學系':7,
    '經營與管理學系':9,'行政管理學系':7};
  for (const [department,count] of Object.entries(counts)) {
    expanded.run(`setRecipientMode('academic'); $('#department-select').value=${JSON.stringify(department)}; updateDepartmentTeachers()`);
    const names = directory.recipients.filter(row=>row.kind==='faculty' && row.department===department).map(row=>row.name);
    assert.equal(names.length,count,department);
    for (const name of names) assert(expanded.get('#academic-teacher-select').innerHTML.includes(name));
    expanded.run(`$('#academic-teacher-select').value=${JSON.stringify(names[0])}; updateAcademicRecipient()`);
    assert.equal(expanded.run('validRecipientSelection()'),true,department);
  }

  const generated = await harness();
  generated.run(`selectRecipientByName('盧陽明'); $('#purpose').value='other';
    draftField('student_name').value='合成學生'; draftField('student_department').value='資訊工程學系';
    draftField('student_grade').value='大四'; draftField('request_details').value='想詢問專題名額與研究方向';`);
  const generationJob = generated.run('submitDraft({preventDefault(){}})');
  assert.equal(generated.calls[0].url,'/api/email-draft');
  assert.equal(generated.calls[0].payload.teacher_name,'盧陽明');
  assert.equal(generated.calls[0].payload.student_department,'資訊工程學系','sender department is independent of selected department');
  assert.equal(generated.calls[0].payload.student_grade,'大四');
  assert(!('recipient_mode' in generated.calls[0].payload));
  assert.equal(generated.get('#department-select').disabled,true,'recipient fields locked during generation');
  await generated.run('submitDraft({preventDefault(){}})');
  assert.equal(generated.calls.length,1,'double submit is blocked');
  generated.pending[0].resolve({...draft,teacher:{teacher_name:'盧陽明'},session:generated.session(0)});
  await generationJob;
  assert.equal(generated.get('#draft-form').hidden,true);
  assert.equal(generated.get('#send-email').disabled,true);
  generated.get('#edit-draft').listeners.click();
  assert.equal(generated.get('#draft-form').hidden,false);
  assert.equal(generated.get('#email-conversation').hidden,true);
  assert.equal(generated.run('draftField("student_name").value'),'合成學生');
  assert.equal(generated.run('state.draft'),null,'returning to form clears send authorization');
  const staleForm = await harness();
  staleForm.run('selectRecipientByName("林朝興")');
  const oldFormJob = staleForm.run('submitDraft({preventDefault(){}})');
  await staleForm.run('resetChat()');
  assert.equal(staleForm.get('#recipient-office').disabled,false);
  assert.equal(staleForm.get('#draft-form [name="student_name"]').disabled,false);
  staleForm.pending[0].resolve({...draft,session:staleForm.session(0)});
  await oldFormJob;
  assert.equal(staleForm.run('state.draft'),null);
  assert.equal(staleForm.run('state.draftSubmitting'),false);
  await answer.run('openDraftForRecipient("國語文學系")');
  const switching = answer.run('confirmEmailRecipientSwitch()');
  await switching;
  assert.equal(answer.calls.length,0,'form switching never calls the model or sends mail');
  assert.equal(answer.run('state.emailRecipientHint'),'國語文學系');
  assert.equal(answer.dom.get('#email-switch-prompt').hidden,true);

  const legacySaved = await harness();
  legacySaved.run(`state.session.account={username:'synthetic'};
    state.memories=[{memory_id:'legacy-template',version:1,title:'合成補交作業',kind:'draft_template',
      content:'合成原文及署名',template_fields:{teacher_name:'許世昌',subject:'合成作業補交詢問'}}];`);
  const applyingLegacy = legacySaved.run('applySavedDraft("legacy-template")');
  assert.equal(legacySaved.calls[0].url,'/api/email-template-draft');
  assert.equal(legacySaved.calls[0].payload.teacher_name,'許世昌','legacy name is resolved only by the authoritative backend');
  legacySaved.pending[0].resolve({draft_id:'legacy-new-draft',teacher:{teacher_name:'許世昌（電機工程學系）'},
    email_draft:{to:'synthetic@example.invalid',subject:'合成作業補交詢問',body:'合成原文及署名'},
    generation:{provider:'saved_draft'},session:{...legacySaved.session(0),account:{username:'synthetic'}}});
  await applyingLegacy;
  assert.equal(legacySaved.run('state.draftTemplateId'),'legacy-template');
  assert.equal(legacySaved.get('#reuse-teacher').value,'許世昌（電機工程學系）');
  assert.equal(legacySaved.get('#draft-body-editor').value,'合成原文及署名');
  assert.equal(legacySaved.get('#confirm-send').checked,false);
  assert.equal(legacySaved.get('#send-email').disabled,true);
  assert.equal(legacySaved.run('state.memories[0].template_fields.teacher_name'),'許世昌','stored template is not rewritten on apply');
  assert(!legacySaved.calls.some(call=>call.url==='/api/email-send'));
  const html = fs.readFileSync(path.join(__dirname,'../ui/index.html'),'utf8');
  assert(!html.includes('id="legacy-draft-fields"'));
  assert.match(html, /id="email-conversation"[^>]*hidden inert/);
  assert.match(html, /id="email-conversation-form"/);
  assert.match(html, /id="email-dialogue"[^>]*role="log"/);
  console.log(JSON.stringify({status:'PASS',groups:25,model_live_status:'LIVE_NOT_RUN',
    checks:['network retry and double click','preview without auto send','reset discards stale reply',
      'main input clears with safe failure recovery','new typing survives email reply and error','Chinese IME Enter protection',
      'grounded teacher and unit actions','recipient handoff and explicit switch confirmation',
      'department-filtered teacher lists','sixteen expanded faculty lists and valid recipient selection','office and missing email handling','office-to-section filtering',
      'office change clears stale section and rejects other-office sections','section handoff and no silent email fallback','Chinese department ten verified faculty options','fixed sender fields and locked payload generation',
      'return to form without auto-send','visible form and hidden historical conversation',
      'successful sandbox send reopens blank default form','already-processed receipt reopens blank default form',
      'post-send answer handoff uses a fresh recipient without stale switch prompt','failed send preserves unfinished draft',
      'pending and completed sends suppress duplicate calls','late send reply cannot restore reset workspace',
      'legacy saved draft selects canonical recipient and preserves original text without sending']},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
