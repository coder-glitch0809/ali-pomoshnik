(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  const groups={pc:'Kompyuter',system:'Tizim',projects:'Loyiha fayllari',coding:'Dasturlash',github:'GitHub',vercel:'Vercel',instagram:'Instagram',phone:'Telefon va joylashuv',knowledge:'Bilimlar va Vault',memory_skills:'Shaxsiy xotira',reminders:'Eslatmalar',agent_admin:'Agentlar boshqaruvi',autopilot_skills:'Avtomatik o‘rganish',market:'Bozor ma’lumotlari'};
  const modes={auto:'Avtomatik',ask:'Tasdiq so‘rasin',deny:'Taqiqlangan'};
  let tools=[],rules={},dirty=false,loaded=false;
  const node=(tag,text,cls)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;};
  // Nom + o'z belgisi (ikonkasi): har bir xizmat belgisidan tanib olinadi
  const titled=(key,name)=>{const b=node('b',undefined,'brand-name');b.insertAdjacentHTML('afterbegin',(window.ALI_ICON_FOR&&window.ALI_ICON_FOR(key))||'');b.append(node('span',name));return b;};
  function setupConnection(c,trigger) {
    const dialog=node('dialog',undefined,'connection-dialog'),form=node('form'),heading=node('h2',c.name+' · Ulash');
    heading.id='connectionTitle';dialog.setAttribute('aria-labelledby',heading.id);
    const close=node('button','Yopish','connection-close');close.type='button';close.onclick=()=>dialog.close();
    const list=node('ol');c.steps.forEach(step=>list.append(node('li',step)));
    const link=node('a',c.link+' ↗','connection-link');link.href=c.url;link.target='_blank';link.rel='noopener noreferrer';
    const status=node('p',undefined,'connection-feedback');status.setAttribute('role','status');
    form.append(heading,close,list,link);
    if(c.can_save){
      form.append(node('p','Rasmiy sahifada tokenni oling, so‘ng shu oynaga qayting. Parolingizni bu yerga kiritmang.'));
      // Firebase kabi JSON kalit - ko'p qatorli maydon; qolganlari - token
      const label=node('label',c.json?'Kalit fayli matni (JSON)':'API token'),input=node(c.json?'textarea':'input');
      if(c.json){input.rows=6;input.spellcheck=false;input.maxLength=20000;}else{input.type='password';input.maxLength=4096;}
      input.autocomplete='off';input.required=true;input.placeholder=c.json?'{ "type": "service_account", ... }':(c.configured?'Almashtirish uchun yangi token':'Tokenni kiriting');label.append(input);
      const save=node('button','Tekshirish va saqlash','connection-save');save.type='submit';
      form.append(label,save);
      form.onsubmit=async event=>{event.preventDefault();save.disabled=true;status.textContent='Ulanish tekshirilmoqda…';
        try{const r=await fetch('/api/connections/'+encodeURIComponent(c.id),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:input.value.trim()})});const data=await r.json();if(!r.ok)throw Error(data.error||(r.status===401?'Avval tizimga kiring.':'Ulanish saqlanmadi.'));input.value='';status.textContent=data.message;await refresh();}
        catch(e){status.textContent=e.message;}finally{save.disabled=false;}
      };
    } else form.onsubmit=event=>event.preventDefault();
    form.append(status);dialog.append(form);document.body.append(dialog);
    dialog.addEventListener('close',()=>{dialog.remove();trigger.focus();},{once:true});dialog.showModal();
  }
  async function request(options) {const r=await fetch('/api/permissions',options);if(!r.ok)throw Error(r.status===401?'Avval tizimga kiring.':'Ruxsatlar saqlanmadi yoki yuklanmadi.');return r.json();}
  function render() {
    const query=$('permissionSearch').value.trim().toLowerCase(),root=$('permissionGroups');root.replaceChildren();
    const sections=new Map();
    for(const tool of tools){
      const title=groups[tool.group]||tool.group;
      if(!`${title} ${tool.name} ${tool.description}`.toLowerCase().includes(query))continue;
      if(!sections.has(tool.group)){const section=node('section',undefined,'permission-card');section.append(node('h2',title));sections.set(tool.group,section);root.append(section);}
      const row=node('label',undefined,'permission-row');const text=node('div');text.append(node('b',tool.name),node('p',tool.description));
      if(tool.dangerous)text.append(node('small','Tashqi amal yoki o‘zgarish kiritishi mumkin','permission-risk'));
      const select=node('select');select.setAttribute('aria-label',tool.name+' ruxsati');
      for(const [value,label] of Object.entries(modes)){if(tool.name==='web_search'&&value==='ask')continue;const option=node('option',label);option.value=value;select.append(option);}
      select.value=rules[tool.name];select.onchange=()=>{rules[tool.name]=select.value;dirty=true;$('permissionsSave').disabled=false;$('permissionsStatus').textContent='O‘zgarishlar hali saqlanmagan.';};
      row.append(text,select);sections.get(tool.group).append(row);
    }
    if(!sections.size)root.append(node('p','Mos vosita topilmadi.'));
  }
  // AI ilovalari (API'siz): o'rnatish -> kirish -> tekshirish; natija serverda eslab qolinadi
  const APP_HINTS={claude:'Oynada /login yozing va Claude akkauntingiz bilan kiring',codex:'Brauzerda “Sign in with ChatGPT” orqali kiring',gemini:'Oynada “Login with Google” ni tanlang'};
  async function aiAppAction(key,action,status,buttons){
    buttons.forEach(b=>b.disabled=true);
    status.textContent={install:'O‘rnatilmoqda… (bir necha daqiqa)',login:'Kirish oynasi ochilmoqda…',verify:'Tekshirilmoqda… (1-3 daqiqa)',forget:'Unutilmoqda…'}[action];
    try{const r=await fetch(`/api/ai-apps/${key}/${action}`,{method:'POST'});const data=await r.json();
      if(!r.ok)throw Error(data.error||'Bajarilmadi');renderAiApps(data);
      const row=document.querySelector(`[data-ai-app="${key}"] .ai-app-status`);if(row&&action!=='verify')row.textContent=data.message;}
    catch(e){status.textContent=e.message;buttons.forEach(b=>b.disabled=false);}
  }
  function renderAiApps(info){
    const root=$('aiApps');if(!root||!info)return;
    const note=info.local?[]:[node('p','Ulash uchun saytni shu kompyuterda oching: http://localhost:8000','ai-apps-note')];
    root.replaceChildren(...note,...info.apps.map(a=>{
      const row=node('div',undefined,'permission-connection');row.dataset.aiApp=a.key;
      const state=!a.installed?'O‘rnatilmagan':a.connected?`✅ Ulangan · ${a.at}`:a.connected===false?`⚠️ Ulanmagan — ${APP_HINTS[a.key]}`:`O‘rnatilgan · ${APP_HINTS[a.key]}`;
      const status=node('span',state,'ai-app-status'),box=node('div',undefined,'ai-app-actions'),buttons=[];
      const add=(label,action,primary)=>{const b=node('button',label,'connection-button'+(primary?' primary':''));b.type='button';b.disabled=!info.local;b.onclick=()=>aiAppAction(a.key,action,status,buttons);buttons.push(b);box.append(b);};
      if(!a.installed)add('O‘rnatish','install',true);
      else if(a.connected){
        if(info.primary===a.key)add('⭐ Asosiy ✓','unprimary',true);else add('⭐ Asosiy qilish','primary');
        add('Tekshirish','verify');add('Unutish','forget');}
      else{add('1. Kirish','login',true);add('2. Tekshirish','verify',true);}
      const mem=node('button','🧠 Xotirani olish','connection-button');mem.type='button';mem.onclick=()=>importMemory(a.key,a.name,mem);box.append(mem);
      row.append(titled(a.key,a.name+(info.primary===a.key?' · asosiy':'')),status,box);return row;}));
    // Saqlangan xotiralar
    const memRow=node('div',undefined,'permission-connection'),memBox=node('div',undefined,'ai-app-actions');
    const add2=(label,fn)=>{const b=node('button',label,'connection-button');b.type='button';b.onclick=()=>fn(b);memBox.append(b);};
    add2('Ko‘rish',()=>{location.hash='vault';});add2('Qo‘lda qo‘shish',b=>importMemory('other','Boshqa',b));
    memRow.append(titled('memory','Saqlangan xotiralar'),node('span',`${info.facts??0} ta fakt eslab qolingan · AI ilovalaridagi xotiralarni ham qo‘shing`,'ai-app-status'),memBox);root.append(memRow);
    // Murabbiy Pro orqali o'qitsin
    const coach=node('div',undefined,'permission-connection'),coachStatus=node('span',info.coach?'Yoqilgan: agentlarni ulangan Pro ilova o‘qitadi':'O‘chiq: Claude API ishlamasa, Pro ilova zaxira bo‘ladi','ai-app-status'),coachBox=node('div',undefined,'ai-app-actions');
    const cb=node('button',info.coach?'O‘chirish':'Yoqish','connection-button'+(info.coach?'':' primary'));cb.type='button';cb.disabled=!info.local;
    cb.onclick=()=>aiAppAction('_coach',info.coach?'off':'on',coachStatus,[cb]);coachBox.append(cb);
    const lb=node('button','▶ Hozir o‘qitish','connection-button primary');lb.type='button';lb.disabled=!info.local||!info.apps.some(x=>x.connected);
    lb.title='Barcha agentlarni ulangan Pro AI’lardan (Claude, ChatGPT, Gemini) o‘qitadi va bilimni xotiraga yozadi';
    lb.onclick=()=>aiAppAction('_coach','learn',coachStatus,[lb,cb]);coachBox.prepend(lb);
    coach.append(titled('_coach','Murabbiy Pro orqali'),coachStatus,coachBox);root.append(coach);
    // Boshqa dasturlar
    // Xizmatlar ilova orqali (token qo'lda kiritilmaydi): GitHub, Vercel
    for(const sv of info.services||[]){
      const row=node('div',undefined,'permission-connection'),box=node('div',undefined,'ai-app-actions'),buttons=[];
      const st=node('span',!sv.installed?'Ilova o‘rnatilmagan':sv.connected?`✅ Ulangan (ilova orqali) · ${sv.at}`:sv.connected===false?`⚠️ ${sv.error||'Ulanmagan'}`:'O‘rnatilgan · brauzer orqali kiring','ai-app-status');
      const add=(label,action,primary)=>{const b=node('button',label,'connection-button'+(primary?' primary':''));b.type='button';b.disabled=!info.local;b.onclick=()=>aiAppAction(sv.key,action,st,buttons);buttons.push(b);box.append(b);};
      if(!sv.installed)add('O‘rnatish','install',true);
      else if(sv.connected){add('Tekshirish','verify');add('Unutish','forget');}
      else{add('1. Kirish','login',true);add('2. Tekshirish','verify',true);}
      row.append(titled(sv.key,sv.name+' ilovasi'),st,box);root.append(row);
    }
    for(const p of info.programs||[]){
      const row=node('div',undefined,'permission-connection'),st=node('span',p.found?'✅ Topildi · Ali loyihalarni shu dasturda ochadi':'O‘rnatilmagan','ai-app-status'),box=node('div',undefined,'ai-app-actions');
      if(p.found){const b=node('button','Ochish','connection-button');b.type='button';b.disabled=!info.local;b.onclick=()=>aiAppAction(p.key,'open',st,[b]);box.append(b);}
      row.append(titled(p.key,p.name),st,box);root.append(row);
    }
  }
  const MEMORY_HOWTO={
    codex:['ChatGPT’ni oching → Sozlamalar → Personalization → Memory → “Manage memories”.','Ro‘yxatni belgilab nusxalang. Yoki ChatGPT’ga yozing: “Men haqimda saqlagan barcha xotiralaringni ro‘yxat qilib ber”.'],
    claude:['claude.ai’ni oching → Settings → Capabilities → Memory → “View and edit memory”.','Matnni nusxalang. Yoki Claude’ga yozing: “Men haqimda eslab qolgan hamma narsani ro‘yxat qilib ber”.'],
    gemini:['gemini.google.com → Sozlamalar → “Saved info” (Saqlangan ma’lumotlar).','Ro‘yxatni nusxalang. Yoki Gemini’ga yozing: “Men haqimda saqlagan ma’lumotlarni ro‘yxat qilib ber”.'],
    other:['Ali eslab qolishi kerak bo‘lgan narsalarni har birini yangi qatorda yozing.']};
  function importMemory(source,name,trigger){
    const dialog=node('dialog',undefined,'connection-dialog'),form=node('form'),close=node('button','Yopish','connection-close');close.type='button';close.onclick=()=>dialog.close();
    const list=node('ol');(MEMORY_HOWTO[source]||MEMORY_HOWTO.other).forEach(s=>list.append(node('li',s)));
    const label=node('label','Xotiralar (har biri yangi qatorda)'),area=node('textarea');area.rows=8;area.required=true;area.maxLength=20000;label.append(area);
    const save=node('button','Ali xotirasiga qo‘shish','connection-save');save.type='submit';const status=node('p',undefined,'connection-feedback');status.setAttribute('role','status');
    const head=node('h2');head.insertAdjacentHTML('afterbegin',(window.ALI_ICON_FOR&&window.ALI_ICON_FOR(source))||window.ALI_ICONS?.memory||'');head.append(' '+name+' · Xotiralarni olish');
    form.append(head,close,list,node('p','Parol, karta raqami kabi maxfiy ma’lumotlarni qo‘shmang.'),label,save,status);dialog.append(form);document.body.append(dialog);
    form.onsubmit=async e=>{e.preventDefault();save.disabled=true;status.textContent='Saqlanmoqda…';
      try{const r=await fetch('/api/memory-import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source,text:area.value})});const d=await r.json();if(!r.ok)throw Error(d.error||'Saqlanmadi');status.textContent=d.message;area.value='';refreshAiApps();}
      catch(err){status.textContent=err.message;}finally{save.disabled=false;}};
    dialog.addEventListener('close',()=>{dialog.remove();trigger.focus();},{once:true});dialog.showModal();
  }
  async function refreshAiApps(){try{const r=await fetch('/api/local-access');if(r.ok)renderAiApps(await r.json());}catch{}}

  document.querySelectorAll('[data-preset]').forEach(b=>b.onclick=async()=>{
    const st=$('presetStatus');st.textContent='Saqlanmoqda…';
    try{const r=await fetch('/api/permissions/preset/'+b.dataset.preset,{method:'POST'});const d=await r.json().catch(()=>({}));
      if(!r.ok)throw Error(d.error||'Saqlanmadi');dirty=false;st.textContent=b.dataset.preset==='computer'?'Kompyuterdagi ishlar endi so‘ramasdan bajariladi':'Barcha xavfli amallar tasdiq so‘raydi';await refresh();}
    catch(e){st.textContent=e.message;}
  });
  async function refresh(){
    refreshAiApps();
    if(dirty)return;
    try{const data=await request();tools=data.tools;rules=Object.fromEntries(tools.map(t=>[t.name,t.mode]));loaded=true;
      $('permissionConnections').replaceChildren(...data.connections.map(c=>{const row=node('div',undefined,'permission-connection');const button=node('button',c.configured?'Sozlash':'Ulash','connection-button');button.type='button';button.setAttribute('aria-label',c.name+' — ulanishni sozlash');button.onclick=()=>setupConnection(c,button);row.append(titled(c.id,c.name),node('span',c.status),button);return row;}));
      $('permissionsStatus').textContent=data.unavailable?'Ruxsatlar faylini o‘qib bo‘lmadi: amallar vaqtincha taqiqlangan.':`${tools.length} ta vosita · Joriy ruxsatlar yuklandi`;
      render();
    }catch(e){$('permissionsStatus').textContent=e.message;}
  }
  $('permissionsSave').onclick=async()=>{
    if(!loaded||!dirty)return;
    $('permissionsSave').disabled=true;
    const snapshot={...rules};
    try{await request({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rules:snapshot})});dirty=JSON.stringify(rules)!==JSON.stringify(snapshot);$('permissionsStatus').textContent=dirty?'Saqlash paytida yangi o‘zgarish kiritildi. Yana saqlang.':'Saqlandi. Ruxsatlar keyingi amaldan boshlab ishlaydi.';}
    catch(e){$('permissionsStatus').textContent=e.message;}finally{$('permissionsSave').disabled=!dirty;}
  };
  $('permissionSearch').oninput=render;
  window.AliPermissions={refresh};
})();
