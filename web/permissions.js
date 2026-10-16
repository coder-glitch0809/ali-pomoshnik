(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  const groups={pc:'Kompyuter',system:'Tizim',projects:'Loyiha fayllari',coding:'Dasturlash',github:'GitHub',vercel:'Vercel',instagram:'Instagram',phone:'Telefon va joylashuv',knowledge:'Bilimlar va Vault',memory_skills:'Shaxsiy xotira',reminders:'Eslatmalar',agent_admin:'Agentlar boshqaruvi',autopilot_skills:'Avtomatik o‘rganish',market:'Bozor ma’lumotlari'};
  const modes={auto:'Avtomatik',ask:'Tasdiq so‘rasin',deny:'Taqiqlangan'};
  let tools=[],rules={},dirty=false,loaded=false;
  const node=(tag,text,cls)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;};
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
      const label=node('label','API token'),input=node('input');input.type='password';input.autocomplete='off';input.required=true;input.maxLength=4096;input.placeholder=c.configured?'Almashtirish uchun yangi token':'Tokenni kiriting';label.append(input);
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
  async function refresh(){
    if(dirty)return;
    try{const data=await request();tools=data.tools;rules=Object.fromEntries(tools.map(t=>[t.name,t.mode]));loaded=true;
      $('permissionConnections').replaceChildren(...data.connections.map(c=>{const row=node('div',undefined,'permission-connection');const button=node('button',c.configured?'Sozlash':'Ulash','connection-button');button.type='button';button.setAttribute('aria-label',c.name+' — ulanishni sozlash');button.onclick=()=>setupConnection(c,button);row.append(node('b',c.name),node('span',c.status),button);return row;}));
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
