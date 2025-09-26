(async ()=>{
  const tg = window.Telegram.WebApp;
  tg.expand();

  const base = window.location.origin;
  const q = (path, opts)=>fetch(base+path, opts).then(r=>r.json());

  const el = id=>document.getElementById(id);
  const output = el('output');
  const balanceEl = el('balance');

  async function refresh(){
    try{
      const res = await q('/api/me');
      balanceEl.innerText = `Баланс: ${res.balance}⭐`;
    }catch(e){
      balanceEl.innerText = `Баланс: — ⭐`;
    }
  }

  el('btn-topup').addEventListener('click', async ()=>{
    const res = await q('/api/topup',{method:'POST'});
    output.innerText = res.message;
    await refresh();
  });

  el('btn-open').addEventListener('click', async ()=>{
    const res = await q('/api/open',{method:'POST'});
    output.innerText = res.message;
    await refresh();
  });

  el('btn-gifts').addEventListener('click', async ()=>{
    const res = await q('/api/gifts');
    output.innerText = res.gifts.length? res.gifts.join(', '): 'Подарков пока нет';
  });

  await refresh();
})();
