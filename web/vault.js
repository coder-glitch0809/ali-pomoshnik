(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const folders = { '':'Barchasi',inbox:'00 · Inbox',identity:'01 · Faktlar',chats:'02 · Suhbatlar',knowledge:'03 · Bilimlar',news:'04 · Yangiliklar',reminders:'05 · Eslatmalar' };
  let folder='', selected='', items=[], timer, generation=0, detailGeneration=0, editing=false;
  const el = (tag, text, cls) => { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(cls)n.className=cls; return n; };
  async function api(url, opts) { const r=await fetch(url,opts); if(r.status===401)throw Error('Qayta tizimga kiring.'); if(!r.ok)throw Error('Xotirani yuklash yoki saqlash amalga oshmadi.'); return r.json(); }
  async function refresh(more=false) {
    const run=++generation;
    try {
      const params=new URLSearchParams({q:$('vaultSearch').value,folder,offset:more?items.length:0});
      const data=await api('/api/vault?'+params); if(run!==generation)return;
      items=more?[...items,...data.items]:data.items;
      $('vaultStatus').textContent=`${data.total} ta yozuv · Server xotirasida saqlanadi · Yangiliklar kunlik o‘rganish orqali qo‘shiladi`;
      $('vaultFolders').replaceChildren();
      for(const [key,name] of Object.entries(folders)) {
        const b=el('button',name,folder===key?'on':''); b.type='button'; b.setAttribute('aria-pressed',String(folder===key));
        b.append(el('small',key?data.counts[key]||0:Object.values(data.counts).reduce((a,b)=>a+b,0)));
        b.onclick=()=>{folder=key;refresh();}; $('vaultFolders').append(b);
      }
      $('vaultList').replaceChildren();
      for(const item of items) { const b=el('button',item.title,item.id===selected?'on':''); b.dataset.id=item.id; b.append(el('small',`${folders[item.folder]} · ${item.updated_at.slice(0,10)}`)); b.onclick=()=>open(item.id); $('vaultList').append(b); }
      if(!items.length)$('vaultList').append(el('p','Yozuv topilmadi.','vault-placeholder'));
      $('vaultMore').hidden=items.length>=data.total;
    } catch(e) { if(run===generation)$('vaultStatus').textContent=e.message; }
  }
  async function open(id) {
    if(editing && !confirm('Saqlanmagan yozuvdan chiqilsinmi?'))return;
    editing=false; const run=++detailGeneration;
    try {
      const row=await api('/api/vault/entry?'+new URLSearchParams({id})); if(run!==detailGeneration)return;
      selected=id; const reader=$('vaultReader'); reader.replaceChildren(el('h2',row.title),el('div',`${folders[row.folder]} · ${row.updated_at.replace('T',' ')}`,'vault-meta'));
      const content=el('div',undefined,'vault-content');
      const parts=row.content.split(/(https?:\/\/[^\s<>"']+)/g);
      for(const part of parts) { if(/^https?:\/\//.test(part)){const a=el('a',part);a.href=part;a.target='_blank';a.rel='noopener noreferrer';content.append(a);}else content.append(document.createTextNode(part)); }
      reader.append(content);
      $('vaultList').querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.id===id));
    }catch(e){$('vaultStatus').textContent=e.message;}
  }
  $('vaultNew').onclick=()=>{
    if(editing && !confirm('Saqlanmagan yozuv o‘rniga yangi yozuv ochilsinmi?'))return;
    ++detailGeneration; editing=true; const form=el('form');
    const title=el('input');title.required=true;title.maxLength=200;
    const text=el('textarea');text.required=true;text.maxLength=20000;
    const label1=el('label','Sarlavha');label1.append(title); const label2=el('label','Yozuv');label2.append(text);
    const button=el('button','Xotiraga saqlash','btn primary');button.type='submit';form.append(label1,label2,button);
    form.onsubmit=async e=>{e.preventDefault();button.disabled=true;try{const result=await api('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:title.value,content:text.value})});editing=false;folder='inbox';$('vaultSearch').value='';await refresh();await open(result.id);}catch(err){$('vaultStatus').textContent=err.message;}finally{button.disabled=false;}};
    $('vaultReader').replaceChildren(el('h2','Yangi yozuv'),form);title.focus();
  };
  $('vaultSearch').oninput=()=>{++generation;clearTimeout(timer);timer=setTimeout(()=>refresh(),250);};
  $('vaultMore').onclick=()=>refresh(true);
  window.AliVault={refresh:()=>refresh()};
  setInterval(()=>{if(!document.hidden&&!$('view-vault').hidden&&!editing&&$('vaultList').scrollTop<8)refresh();},30000);
})();
