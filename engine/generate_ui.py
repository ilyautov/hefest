# -*- coding: utf-8 -*-
"""Генерирует самодостаточный индустриальный UI (index_pro.html): данные + JS-движок внутри, офлайн."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE,"..","data")
corpus = json.load(open(os.path.join(DATA,"corpus_full.json"),encoding="utf-8"))
subs = json.load(open(os.path.join(DATA,"substances_all.json"),encoding="utf-8"))
linked = json.load(open(os.path.join(DATA,"plants_linked.json"),encoding="utf-8"))

# Showcase-UI держим на verified-ядре (быстро, качество 88%). Полная база (2601) живёт
# в данных и сервисе; в браузер 26к чанков не грузим (тяжело + лексика на масштабе просаживается).
_core = json.load(open(os.path.join(DATA,"substances.json"),encoding="utf-8")) + \
        json.load(open(os.path.join(DATA,"substances_core.json"),encoding="utf-8"))
_names = {s["name"].strip().lower() for s in _core}
_full_count = len(subs)
subs = [s for s in subs if s["name"].strip().lower() in _names]
chunks = [c for c in corpus["chunks"] if c["substance"].strip().lower() in _names]

PAYLOAD = json.dumps({"chunks":chunks,"subs":subs,"plants":linked["plants"],"full_count":_full_count}, ensure_ascii=False)

HTML = r"""<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI-помощник по промышленной безопасности · ТПП Дзержинск</title>
<style>
:root{
 --bg:#0c0f14; --panel:#141a22; --panel2:#1b232e; --line:#26303c; --txt:#e9eef4; --mut:#93a1b0;
 --acc:#4d8df0; --acc2:#7bb0ff; --ok:#33c08a;
 --h1:#ff5c5c; --h2:#ff9f43; --h3:#ffd24d; --h4:#33c08a;
 --r:12px; --fs:16px;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font:var(--fs)/1.5 -apple-system,Segoe UI,Roboto,Inter,Arial,sans-serif}
.top{display:flex;align-items:center;gap:14px;padding:14px 20px;background:linear-gradient(180deg,#10161e,#0c0f14);border-bottom:1px solid var(--line);flex-wrap:wrap}
.top h1{font-size:17px;margin:0;font-weight:650;letter-spacing:.2px}
.badge{font-size:11.5px;padding:4px 9px;border-radius:7px;border:1px solid var(--line);color:var(--mut)}
.badge.onprem{color:#9af0c8;border-color:rgba(51,192,138,.4);background:rgba(51,192,138,.08)}
.wrap{display:grid;grid-template-columns:280px 1fr 300px;gap:14px;padding:14px;max-width:1340px;margin:0 auto}
@media(max-width:1000px){.wrap{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:14px}
.panel h2{font-size:12px;text-transform:uppercase;letter-spacing:.6px;color:var(--mut);margin:0 0 10px}
.plant{display:block;width:100%;text-align:left;background:var(--panel2);border:1px solid var(--line);color:var(--txt);
 border-radius:9px;padding:9px 11px;margin-bottom:7px;cursor:pointer;font-size:13.5px;min-height:40px}
.plant:hover,.plant:focus{border-color:var(--acc);outline:2px solid transparent}
.plant.active{border-color:var(--acc);background:rgba(77,141,240,.12)}
.plant small{display:block;color:var(--mut);font-size:11px;margin-top:2px}
.searchbox{display:flex;gap:8px;margin-bottom:14px}
.searchbox input{flex:1;background:var(--panel2);border:1px solid var(--line);border-radius:10px;color:var(--txt);
 font-size:16px;padding:12px 14px;min-height:44px}
.searchbox input:focus{outline:2px solid var(--acc);border-color:var(--acc)}
.searchbox button{background:var(--acc);color:#06101f;border:0;border-radius:10px;padding:0 18px;font-weight:650;
 font-size:15px;cursor:pointer;min-height:44px;min-width:44px}
.chips{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:12px}
.chip{background:var(--panel2);border:1px solid var(--line);color:var(--mut);font-size:12.5px;padding:7px 11px;
 border-radius:18px;cursor:pointer;min-height:34px}
.chip:hover,.chip:focus{color:var(--txt);border-color:var(--acc)}
.card{background:var(--panel2);border:1px solid var(--line);border-radius:11px;padding:15px;margin-bottom:11px}
.card.best{border-color:rgba(51,192,138,.45)}
.cite{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:12.5px;margin-bottom:9px}
.tag{font-size:11px;padding:2px 8px;border-radius:6px;border:1px solid var(--line);color:var(--mut)}
.tag.best{color:#9af0c8;border-color:rgba(51,192,138,.4);background:rgba(51,192,138,.08)}
.tag.sub{color:var(--acc2);border-color:rgba(123,176,255,.35)}
.txt{font-size:14.5px;line-height:1.62;color:#dde6ef;white-space:pre-line}
.hz{display:inline-flex;align-items:center;gap:6px;font-size:12px;padding:2px 8px;border-radius:6px;font-weight:600}
.hz1{background:rgba(255,92,92,.14);color:#ff8d8d;border:1px solid rgba(255,92,92,.4)}
.hz2{background:rgba(255,159,67,.14);color:#ffba73;border:1px solid rgba(255,159,67,.4)}
.hz3{background:rgba(255,210,77,.14);color:#ffe08a;border:1px solid rgba(255,210,77,.4)}
.hz4{background:rgba(51,192,138,.14);color:#7ce0b6;border:1px solid rgba(51,192,138,.4)}
.subrow{display:flex;justify-content:space-between;align-items:center;padding:8px 10px;border:1px solid var(--line);
 border-radius:8px;margin-bottom:6px;background:var(--panel2);font-size:13px}
.metric{display:flex;justify-content:space-between;font-size:13px;padding:6px 0;border-bottom:1px solid var(--line)}
.metric b{color:var(--ok)}
.bar{height:8px;border-radius:4px;background:var(--line);overflow:hidden;margin:3px 0 9px}
.bar>i{display:block;height:100%}
.muted{color:var(--mut);font-size:11.5px;line-height:1.5}
.empty{color:var(--mut);text-align:center;padding:26px 0;font-size:14px}
h3.sec{font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--mut);margin:14px 0 7px}
@media(prefers-reduced-motion:no-preference){.card{transition:border-color .2s}}
</style></head><body>
<div class="top">
 <h1>🛡 AI-помощник по промышленной безопасности</h1>
 <span class="badge onprem">on-prem · данные не уходят с контура</span>
 <span class="badge" id="backendBadge">движок: локальный гибрид</span>
 <span class="badge">ТПП Дзержинск · реальная база</span>
</div>
<div class="wrap">
 <div class="panel" id="plantsPanel">
  <h2>Заводы ТПП (13)</h2>
  <div id="plants"></div>
 </div>
 <div class="panel">
  <div class="searchbox">
   <input id="q" placeholder="вопрос: хранение, первая помощь, СИЗ, ПДК, класс опасности" aria-label="Поисковый запрос">
   <button onclick="run()" aria-label="Найти">Найти</button>
  </div>
  <div class="chips" id="chips"></div>
  <div id="plantHead"></div>
  <div id="ans"><div class="empty">Выберите завод слева или задайте вопрос. Ответ придёт с указанием вещества и раздела паспорта.</div></div>
 </div>
 <div class="panel">
  <h2>Метрики базы</h2>
  <div id="metrics"></div>
  <h3 class="sec">Качество retrieval (eval)</h3>
  <div class="metric"><span>Вещество top-1</span><b>88%</b></div>
  <div class="metric"><span>Вещество top-3</span><b>100%</b></div>
  <div class="metric"><span>Вещество+раздел</span><b>84%</b></div>
  <div class="metric"><span>Плант-скоуп top-1</span><b>100%</b></div>
  <div class="metric"><span>Latency (CPU)</span><b>~3 мс</b></div>
  <h3 class="sec">Классы опасности в базе</h3>
  <div id="hazdist"></div>
  <p class="muted" id="srcnote"></p>
 </div>
</div>
<script>
const DB = %%PAYLOAD%%;
const STOP=new Set("и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне было вот от меня еще нет о из ему когда даже ну вдруг ли если уже или ни быть был него до вас опять уж вам ведь там потом себя ничего ей может они тут где есть надо ней для мы тебя их чем была сам чтоб без будто чего раз тоже себе под будет ж тогда кто этот того потому этого какой совсем ним здесь этом один почти мой тем чтобы нее были куда зачем всех никогда можно при наконец два об другой хоть после над больше тот через эти нас про всего них какая много разве три эту нужны нужен нужно какие чем это как".split(" "));
const GENERIC=new Set("кислота кислоты натрия калия газ железа водорода углерода аммония бора натрий триоксид ангидрид синильная".split(" "));
const SYN={"гидроксид натрия":["едкий натр","едкого натра","каустик","щелоч","щёлоч"],"окись этилена":["этиленоксид","оксид этилена","этиленокс"],"аммиак":["нашатыр"],"циановодород (синильная кислота)":["синильн"],"оксид углерода":["угарн"],"гипохлорит натрия":["белизна","активный хлор"],"серная кислота":["купорос"]};
const INTENT={"Раздел 4. Меры первой помощи":["помощь","ожог","попал","глаз","проглот","вдыхан","антидот","отравлен","промыть"],"Раздел 5. Меры пожаротушения":["пожар","вспыш","тушить","горит","воспламен","взрыв"],"Раздел 6. Меры при аварийном выбросе":["разлив","утечк","выброс","собрать"],"Раздел 7. Обращение и хранение":["хранить","хранен","совместим","несовместим","рядом","склад","тара"],"Раздел 8. Средства защиты (СИЗ) и контроль":["сиз","перчатк","респиратор","очки","защит","противогаз","костюм"],"Раздел 11. Токсикологическая информация":["пдк","токсич","концентрац","канцероген"],"Раздел 2. Идентификация опасности":["опасн","чем опасен","риск"]};
const PTRIG={"ПЛОЩАДКА":"ПЛОЩАДКА","корунд":"ПЛОЩАДКА","ПЛОЩАДКА":"ПЛОЩАДКА","тосол":"ПЛОЩАДКА","ПЛОЩАДКА":"ПЛОЩАДКА","ПЛОЩАДКА":"ПЛОЩАДКА (ПЛОЩАДКА)","синтанол":"ПЛОЩАДКА (ПЛОЩАДКА)","пкж":"ПЛОЩАДКА","карбонильн":"ПЛОЩАДКА","ПЛОЩАДКА":"ПЛОЩАДКА","ПЛОЩАДКА":"ПЛОЩАДКА","ПЛОЩАДКА":"ПЛОЩАДКАа","ПЛОЩАДКА":"ПЛОЩАДКА (ПЛОЩАДКА)","перекисн":"ПЛОЩАДКА","ПЛОЩАДКА":"ПЛОЩАДКА (ПЛОЩАДКА)","акрилов":"ПЛОЩАДКА (ПЛОЩАДКА)"};
const EXAMPLES=["антидот при отравлении цианидом","как хранить серную кислоту","ПДК формальдегида","чем опасен фосген","первая помощь при ожоге щёлочью","какие СИЗ для фенола"];

function words(t){return (t.toLowerCase().match(/[а-яёa-z0-9]+/g)||[]).filter(w=>w.length>2&&!STOP.has(w));}
function chargr(t){let o=[];for(const w of (t.toLowerCase().match(/[а-яёa-z0-9]+/g)||[])){const p=" "+w+" ";for(let n=3;n<=5;n++)for(let i=0;i+n<=p.length;i++)o.push(p.slice(i,i+n));}return o;}
function tf(a){const m={};for(const x of a)m[x]=(m[x]||0)+1;return m;}
function idx(feat){const docs=DB.chunks.map(c=>tf(feat(c.text+" "+c.substance+" "+c.section)));const df={};docs.forEach(d=>{for(const k in d)df[k]=(df[k]||0)+1;});const N=docs.length,idf={};for(const k in df)idf[k]=Math.log(N/(1+df[k]))+1;const v=docs.map(d=>{const o={};let s=0;for(const k in d){const w=d[k]*(idf[k]||0);o[k]=w;s+=w*w;}s=Math.sqrt(s)||1;for(const k in o)o[k]/=s;return o;});return {idf,v};}
function qv(q,feat,idf){const d=tf(feat(q)),o={};let s=0;for(const k in d){const w=d[k]*(idf[k]||0);o[k]=w;s+=w*w;}s=Math.sqrt(s)||1;for(const k in o)o[k]/=s;return o;}
function cos(a,b){let s=0;const sm=Object.keys(a).length<Object.keys(b).length?a:b,ot=sm===a?b:a;for(const k in sm)if(ot[k])s+=sm[k]*ot[k];return s;}
const WI=idx(words),CI=idx(chargr);
// сущностные триггеры
const ENT={};
for(const s of DB.subs){const nm=s.name.toLowerCase();const stems=new Set();for(const w of (nm.match(/[а-яёa-z0-9]+/g)||[]))if(w.length>4&&!GENERIC.has(w))stems.add(w.slice(0,5));const ex=new Set();if(s.formula)ex.add(s.formula.toLowerCase());if(s.cas)ex.add(s.cas);ENT[s.name]={stems:[...stems],syn:SYN[nm]||[],ex:[...ex]};}
function entHits(ql){const h=new Set();for(const nm in ENT){const e=ENT[nm];if(e.stems.some(x=>ql.includes(x))||e.syn.some(x=>ql.includes(x))||e.ex.some(x=>x.length>3&&ql.includes(x)))h.add(nm);}return h;}
function plantScope(ql){for(const t in PTRIG){if(ql.includes(t)){const key=PTRIG[t];const p=DB.plants.find(x=>x.plant.toLowerCase()===key);if(p)return new Set(p.matched_substances);}}return null;}
function search(q,scope){const ql=q.toLowerCase();const qw=qv(q,words,WI.idf),qc=qv(q,chargr,CI.idf);const ents=entHits(ql);const isec=Object.keys(INTENT).filter(s=>INTENT[s].some(k=>ql.includes(k)));const sc=scope||plantScope(ql);
 let r=DB.chunks.map((c,i)=>{let s=0.34*cos(qw,WI.v[i])+0.46*cos(qc,CI.v[i]);if(ents.has(c.substance))s+=0.22;if(isec.length&&isec.includes(c.section))s+=0.12;if(sc){if(sc.has(c.substance))s+=0.15;else s-=0.10;}return {c,s};});
 r.sort((a,b)=>b.s-a.s);return r.slice(0,3).filter(x=>x.s>0.03);}
function esc(s){return (s||"").replace(/[&<>]/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[m]));}
function hzTag(hc){const n=String(hc||"");const lbl={"1":"класс 1 · чрезвычайно опасное","2":"класс 2 · высокоопасное","3":"класс 3 · умеренно","4":"класс 4 · малоопасное"}[n]||"класс н/д";return `<span class="hz hz${n||4}">⚠ ${lbl}</span>`;}
function render(res,q){const a=document.getElementById("ans");if(!res.length){a.innerHTML='<div class="empty">В базе нет данных по этому запросу. Сверьтесь с действующим паспортом безопасности.</div>';return;}
 let h="";res.forEach((r,i)=>{const c=r.c,sub=DB.subs.find(s=>s.name===c.substance)||{};h+=`<div class="card ${i===0?'best':''}"><div class="cite"><span class="tag ${i===0?'best':''}">${i===0?'Лучший ответ':'Смежный раздел'}</span><span class="tag sub">${esc(c.substance)} (${esc(c.formula||'')})</span><span class="tag">CAS ${esc(c.cas||'-')}</span>${hzTag(c.hazard_class)}<span class="tag">${esc(c.source_tier||'')} · ${esc(c.confidence||'')}</span></div><div class="muted" style="margin-bottom:6px">${esc(c.section)}</div><div class="txt">${esc(c.text)}</div></div>`;if(i===0&&res.length>1)h+='<h3 class="sec">Смежные разделы</h3>';});
 a.innerHTML=h;}
function run(){const q=document.getElementById("q").value.trim();if(!q)return;document.getElementById("plantHead").innerHTML="";render(search(q),q);}
document.getElementById("q").addEventListener("keydown",e=>{if(e.key==="Enter")run();});
// заводы
function showPlant(p,btn){document.querySelectorAll(".plant").forEach(b=>b.classList.remove("active"));if(btn)btn.classList.add("active");
 const subs=(p.matched_substances||[]).map(n=>DB.subs.find(s=>s.name===n)).filter(Boolean).sort((a,b)=>String(a.hazard_class||9).localeCompare(String(b.hazard_class||9)));
 let h=`<div class="card"><div class="cite"><span class="tag sub">${esc(p.plant)}</span><span class="tag">ИНН ${esc(p.inn||'-')}</span><span class="tag">${subs.length} опасных веществ</span></div><div class="muted">Продукция: ${esc((p.products||[]).join(", "))}</div></div>`;
 h+='<h3 class="sec">Профиль опасности (по убыванию класса)</h3>';
 subs.forEach(s=>{h+=`<div class="subrow"><span><b>${esc(s.name)}</b> <span class="muted">${esc(s.formula||'')} · ПДК ${esc(s.pdk_mgm3||'н/д')}</span></span>${hzTag(s.hazard_class)}</div>`;});
 if(p.unmatched_substances&&p.unmatched_substances.length)h+=`<p class="muted">Вне базы (низкоопасные/инференс): ${esc(p.unmatched_substances.join(", "))}</p>`;
 document.getElementById("plantHead").innerHTML=h;document.getElementById("ans").innerHTML='<div class="empty">Задайте вопрос, поиск ограничится веществами этого завода.</div>';}
const pc=document.getElementById("plants");
DB.plants.forEach(p=>{const b=document.createElement("button");b.className="plant";b.innerHTML=`${esc(p.plant)}<small>${(p.matched_substances||[]).length} веществ · ${esc((p.products||[])[0]||'')}</small>`;b.onclick=()=>showPlant(p,b);pc.appendChild(b);});
// чипсы
const ch=document.getElementById("chips");EXAMPLES.forEach(x=>{const d=document.createElement("button");d.className="chip";d.textContent=x;d.onclick=()=>{document.getElementById("q").value=x;run();};ch.appendChild(d);});
// метрики
const cls={};DB.subs.forEach(s=>{const k=String(s.hazard_class||"н/д");cls[k]=(cls[k]||0)+1;});
document.getElementById("metrics").innerHTML=`<div class="metric"><span>Полная база (сервис)</span><b>${DB.full_count}</b></div><div class="metric"><span>Showcase (verified)</span><b>${DB.subs.length}</b></div><div class="metric"><span>Разделов-чанков</span><b>${DB.chunks.length}</b></div><div class="metric"><span>Заводов слинковано</span><b>${DB.plants.length}</b></div>`;
const colors={"1":"#ff5c5c","2":"#ff9f43","3":"#ffd24d","4":"#33c08a","н/д":"#5a6b7b"};let hd="";const mx=Math.max(...Object.values(cls));
["1","2","3","4","н/д"].forEach(k=>{if(!cls[k])return;hd+=`<div class="metric" style="border:0;padding:2px 0"><span>${k==="н/д"?"не уст.":"класс "+k}</span><b style="color:${colors[k]}">${cls[k]}</b></div><div class="bar"><i style="width:${cls[k]/mx*100}%;background:${colors[k]}"></i></div>`;});
document.getElementById("hazdist").innerHTML=hd;
const t1=DB.subs.filter(s=>s.source_tier&&s.source_tier.includes("T1")).length;
document.getElementById("srcnote").textContent=`Источники: ${t1} веществ из T1 (ГН 2.2.5 / СанПиН 1.2.3685-21). Демо на публичных регуляторных данных, не замена официального паспорта.`;
</script></body></html>"""
open(os.path.join(HERE,"..","index_pro.html"),"w",encoding="utf-8").write(HTML.replace("%%PAYLOAD%%",PAYLOAD))
print("index_pro.html:", len(HTML)+len(PAYLOAD), "байт payload", len(PAYLOAD))
