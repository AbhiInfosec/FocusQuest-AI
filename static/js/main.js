/* FocusQuest AI v3 — Premium */

// ── API helper ──
async function api(method,path,body){
  const o={method,headers:{'Content-Type':'application/json'}};
  if(body)o.body=JSON.stringify(body);
  try{const r=await fetch(path,o);return r.json()}
  catch(e){console.error(e);return{error:'Network error'}}
}

// ── Toasts ──
function showXP(n,label='XP'){
  const el=document.getElementById('xp-toast');if(!el)return;
  el.textContent=`+${n} ${label} ⚡`;el.classList.add('show');
  setTimeout(()=>el.classList.remove('show'),2500);
}
function showBadge(key){
  const el=document.getElementById('badge-toast');if(!el)return;
  const names={first_topic:'First Step 🎯',streak_3:'Hat-Trick 🔥',streak_7:'Week Warrior ⚡',streak_30:'Monthly Master 💎',xp_500:'XP Hunter ⭐',xp_2000:'XP Legend 🏆',quiz_ace:'Quiz Ace 🧠',daily_champ:'Daily Champion 🎖️',speed_quiz_5:'Speed Racer 🏎️',ai_user:'AI Scholar 🤖',subject_5:'Multi-Tasker 📚',night_owl:'Night Owl 🦉'};
  el.innerHTML=`🏅 New Badge Unlocked!<br><strong>${names[key]||key}</strong>`;
  el.classList.add('show');setTimeout(()=>el.classList.remove('show'),4000);
}

// ── Auth ──
async function logout(){await api('POST','/api/auth/logout');location.href='/login'}

// ── Sidebar ──
function toggleSidebar(){document.getElementById('sidebar')?.classList.toggle('open')}
document.addEventListener('click',e=>{
  const sb=document.getElementById('sidebar'),mb=document.getElementById('menu-btn');
  if(sb?.classList.contains('open')&&!sb.contains(e.target)&&e.target!==mb)sb.classList.remove('open');
});

// ── Theme ──
function toggleTheme(){
  const h=document.documentElement,d=h.getAttribute('data-theme')==='dark';
  h.setAttribute('data-theme',d?'light':'dark');
  const b=document.getElementById('theme-btn');
  if(b)b.textContent=d?'☀️ Light':'🌙 Dark';
  localStorage.setItem('fq-theme',d?'light':'dark');
}
const _st=localStorage.getItem('fq-theme')||'dark';
document.documentElement.setAttribute('data-theme',_st);

// ── Motivation Quotes (local bank — works offline too) ──
const QUOTES=[
  {text:"The secret of getting ahead is getting started.",author:"Mark Twain"},
  {text:"It always seems impossible until it's done.",author:"Nelson Mandela"},
  {text:"Don't watch the clock; do what it does. Keep going.",author:"Sam Levenson"},
  {text:"The expert in anything was once a beginner.",author:"Helen Hayes"},
  {text:"Success is the sum of small efforts repeated day in and day out.",author:"Robert Collier"},
  {text:"Education is the most powerful weapon you can use to change the world.",author:"Nelson Mandela"},
  {text:"The more that you read, the more things you will know.",author:"Dr. Seuss"},
  {text:"An investment in knowledge pays the best interest.",author:"Benjamin Franklin"},
  {text:"The beautiful thing about learning is that no one can take it away from you.",author:"B.B. King"},
  {text:"Study hard, for the well is deep, and our brains are shallow.",author:"Richard Baxter"},
  {text:"There are no shortcuts to any place worth going.",author:"Beverly Sills"},
  {text:"The harder you work for something, the greater you'll feel when you achieve it.",author:"Anonymous"},
  {text:"Believe you can and you're halfway there.",author:"Theodore Roosevelt"},
  {text:"Small daily improvements over time lead to stunning results.",author:"Robin Sharma"},
  {text:"Your limitation—it's only your imagination.",author:"Anonymous"},
  {text:"Push yourself, because no one else is going to do it for you.",author:"Anonymous"},
  {text:"Great things never come from comfort zones.",author:"Anonymous"},
  {text:"Dream it. Wish it. Do it.",author:"Anonymous"},
  {text:"Success doesn't just find you. You have to go out and get it.",author:"Anonymous"},
  {text:"The harder the battle, the sweeter the victory.",author:"Les Brown"},
  {text:"Don't stop when you're tired. Stop when you're done.",author:"Anonymous"},
  {text:"Wake up with determination. Go to bed with satisfaction.",author:"Anonymous"},
  {text:"Do something today that your future self will thank you for.",author:"Sean Patrick Flanery"},
  {text:"Little things make big days.",author:"Anonymous"},
  {text:"It's going to be hard, but hard does not mean impossible.",author:"Anonymous"},
];
function getDailyQuote(){
  const idx=(new Date().getDate()+new Date().getMonth()*31)%QUOTES.length;
  return QUOTES[idx];
}
function getRandomQuote(){return QUOTES[Math.floor(Math.random()*QUOTES.length)]}

// ── User bar ──
async function loadUserBar(){
  try{
    const d=await api('GET','/api/auth/me');
    if(d.error)return;
    const g=id=>document.getElementById(id);
    if(g('sidebar-name'))g('sidebar-name').textContent=d.name;
    if(g('sidebar-level'))g('sidebar-level').textContent=`Lv${d.level} · ${d.level_name}`;
    if(g('user-avatar')){g('user-avatar').textContent=d.name[0].toUpperCase()}
    if(g('topbar-xp'))g('topbar-xp').textContent=`${d.xp} XP`;
    if(g('topbar-streak'))g('topbar-streak').textContent=d.streak;
    const b=document.getElementById('theme-btn');
    if(b)b.textContent=_st==='dark'?'🌙 Dark':'☀️ Light';
  }catch{}
}

// ── Utils ──
function daysUntil(iso){const n=new Date();n.setHours(0,0,0,0);return Math.round((new Date(iso)-n)/86400000)}

// ── Tour ──
const TOUR=[
  {icon:'🌌',title:'Welcome to FocusQuest AI!',desc:'Your AI-powered gamified study universe. Built to make studying fun, smart and actually rewarding!'},
  {icon:'🤖',title:'Study AI — Your Secret Weapon',desc:'Upload any syllabus → AI instantly creates Short Notes, Long Notes, Practice Questions, Quiz and Schedule!'},
  {icon:'⏱️',title:'Anti-Cheat Study Timer',desc:'Server-verified timer. You cannot fake study hours. Complete timer → AI Quiz → Reflection → +50 XP!'},
  {icon:'🎮',title:'Games & Challenges',desc:'Speed Quiz, Flash Cards, Daily Challenge (+100 XP), Weekly Tournament and Streak Battle with friends!'},
  {icon:'🏆',title:'XP, Levels & Badges',desc:'Topics +50 XP, Quizzes +30 XP, Streak +20 XP, Daily Challenge +100 XP. Unlock 15 achievement badges!'},
  {icon:'🚀',title:"You're Ready — Launch!",desc:'Add your subjects, upload your syllabus, and start your quest. The universe of knowledge is yours!'},
];
let _ts=0;
function startTour(){document.getElementById('tour-overlay')?.classList.remove('hidden');_ts=0;_rt()}
function _rt(){
  const s=TOUR[_ts];
  document.getElementById('tour-icon').textContent=s.icon;
  document.getElementById('tour-title').textContent=s.title;
  document.getElementById('tour-desc').textContent=s.desc;
  document.getElementById('tour-steps').innerHTML=TOUR.map((_,i)=>`<div class="tour-step ${i===_ts?'active':''}"></div>`).join('');
  const b=document.getElementById('tour-next');
  if(b)b.textContent=_ts===TOUR.length-1?'🚀 Start Quest!':'Next →';
}
function nextTour(){if(_ts<TOUR.length-1){_ts++;_rt()}else endTour()}
function endTour(){document.getElementById('tour-overlay')?.classList.add('hidden');localStorage.setItem('fq-tour-done','1')}

// ── Init ──
document.addEventListener('DOMContentLoaded',()=>{
  if(document.getElementById('sidebar'))loadUserBar();
  if(!localStorage.getItem('fq-tour-done')&&document.getElementById('sidebar'))setTimeout(startTour,1000);
});
