(() => {
  const status=document.getElementById('status'),retry=document.getElementById('retry');
  async function open(){
    retry.hidden=true;const app=window.Telegram?.WebApp;
    if(!app?.initData){status.textContent='Bu shaxsiy panel. Telegram’da Ali botiga /start yuboring va Mini App tugmasini bosing.';return;}
    app.ready();app.expand();status.textContent='Telegram hisobingiz tekshirilmoqda…';
    try {
      const r=await fetch('/api/telegram/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:app.initData})});
      const data=await r.json();
      if(!r.ok){status.textContent=data.error||'Kirish tasdiqlanmadi. Botdagi tugmadan qayta oching.';return;}
      status.textContent='Xush kelibsiz, Abbos!';location.replace('/');
    }catch{status.textContent='Server bilan aloqa uzildi. Qayta urinib ko‘ring.';retry.hidden=false;}
  }
  retry.onclick=open;open();
})();
