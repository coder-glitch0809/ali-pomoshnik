(() => {
  const status=document.getElementById('status'),retry=document.getElementById('retry'),spin=document.getElementById('spin');
  const done=(text,canRetry)=>{status.textContent=text;spin.hidden=true;retry.hidden=!canRetry;};
  // telegram-web-app.js async yuklanadi: tayyor bo'lishini 8 soniyagacha kutamiz.
  function waitTelegram(ms){
    return new Promise(resolve=>{const start=Date.now();(function poll(){
      const app=window.Telegram?.WebApp;
      if(app?.initData||Date.now()-start>ms)return resolve(app);
      setTimeout(poll,120);})();});
  }
  async function open(){
    retry.hidden=true;spin.hidden=false;status.textContent='Telegram hisobingiz tekshirilmoqda…';
    const app=await waitTelegram(8000);
    if(!window.Telegram)return done('Telegram skripti yuklanmadi (internet sekin yoki telegram.org yopiq). Qayta urinib ko‘ring.',true);
    if(!app?.initData)return done('Bu shaxsiy panel. Telegram’da Ali botiga /start yuboring va “Ali panel” tugmasini bosing.',false);
    app.ready();app.expand();
    try{app.setHeaderColor('#090e1d');app.setBackgroundColor('#090e1d');}catch{}
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
    try{
      const r=await fetch('/api/telegram/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:app.initData}),signal:controller.signal});
      const data=await r.json().catch(()=>({}));
      if(!r.ok)return done(data.error||'Kirish tasdiqlanmadi. Botdagi tugmadan qayta oching.',r.status>=500);
      status.textContent='Xush kelibsiz, Abbos! Panel ochilmoqda…';location.replace('/');
    }catch{done('Server javob bermadi (u uyg‘onayotgan bo‘lishi mumkin). Bir necha soniyadan keyin qayta urining.',true);}
    finally{clearTimeout(timer);}
  }
  retry.onclick=open;open();
})();
