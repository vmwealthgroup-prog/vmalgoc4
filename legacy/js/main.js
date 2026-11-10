const m=document.getElementById('menu'),l=document.getElementById('links');
if(m)m.addEventListener('click',()=>{const o=l.classList.toggle('open');m.setAttribute('aria-expanded',o)});
const rows=[...document.querySelectorAll('[data-ltp]')];
if(rows.length&&!matchMedia('(prefers-reduced-motion:reduce)').matches){
 setInterval(()=>rows.forEach(r=>{let v=+r.dataset.ltp,d=(Math.random()-.5)*4;v=Math.max(1,v+d);r.dataset.ltp=v;
  r.textContent=v.toFixed(2);r.className=d>=0?'up':'dn'}),1300);}
