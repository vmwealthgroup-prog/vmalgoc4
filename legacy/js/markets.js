// Public Coinbase market-data feed. No API key is used or needed in the browser. NEVER put exchange keys in front-end code.
const PAIRS=['BTC-USD','ETH-USD','SOL-USD','XRP-USD'];
const tbody=document.getElementById('mk'),stat=document.getElementById('mstat');
const px={};
tbody.innerHTML=PAIRS.map(p=>`<tr><td>${p.replace('-','/')}</td><td id="p-${p}">—</td><td id="b-${p}">—</td><td id="a-${p}">—</td></tr>`).join('');
const fmt=v=>(+v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
function apply(msg){
  if(msg.channel!=='ticker'||!msg.events)return;
  for(const ev of msg.events)for(const t of ev.tickers||[]){
    const id=t.product_id,el=document.getElementById('p-'+id);if(!el)continue;
    const old=px[id];px[id]=+t.price;el.textContent=fmt(t.price);
    if(old!==undefined)el.className=px[id]>=old?'up':'dn';
    if(t.best_bid)document.getElementById('b-'+id).textContent=fmt(t.best_bid);
    if(t.best_ask)document.getElementById('a-'+id).textContent=fmt(t.best_ask);}
}
function connect(){
  stat.textContent='Connecting…';
  const ws=new WebSocket('wss://advanced-trade-ws.coinbase.com');
  ws.onopen=()=>{ws.send(JSON.stringify({type:'subscribe',product_ids:PAIRS,channel:'ticker'}));
                 ws.send(JSON.stringify({type:'subscribe',product_ids:PAIRS,channel:'heartbeats'}));stat.textContent='Live (Coinbase public feed)'};
  ws.onmessage=e=>{try{apply(JSON.parse(e.data))}catch(_){}};
  ws.onclose=()=>{stat.textContent='Disconnected. Retrying in 5s…';setTimeout(connect,5000)};
  ws.onerror=()=>ws.close();
}
if(typeof window!=='undefined'&&tbody)connect();
if(typeof module!=='undefined')module.exports={apply};
