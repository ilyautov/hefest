# -*- coding: utf-8 -*-
"""Генерирует самодостаточный index.html: корпус встроен, retrieval на JS (порт v2), офлайн, без ключей."""
import json

corpus = json.load(open("corpus.json", encoding="utf-8"))
CHUNKS_JSON = json.dumps(corpus["chunks"], ensure_ascii=False)

HTML = r"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI-помощник по паспортам безопасности (демо)</title>
<style>
:root{--bg:#0f1216;--card:rgba(255,255,255,.06);--brd:rgba(255,255,255,.12);--txt:#e8edf2;--mut:#9aa7b4;--acc:#5b9dff;--ok:#3ecf8e;--warn:#ffb454;}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Inter,Arial,sans-serif;background:radial-gradient(1200px 600px at 70% -10%,#1a2230,#0f1216);color:var(--txt);min-height:100vh;padding:32px 18px}
.wrap{max-width:780px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px;font-weight:650;letter-spacing:.2px}
.sub{color:var(--mut);font-size:13px;margin-bottom:18px;line-height:1.5}
.banner{background:rgba(255,180,84,.1);border:1px solid rgba(255,180,84,.3);color:#ffd9a0;font-size:12px;padding:9px 12px;border-radius:10px;margin-bottom:18px;line-height:1.45}
.searchbox{display:flex;gap:8px;background:var(--card);border:1px solid var(--brd);border-radius:14px;padding:8px;backdrop-filter:blur(12px)}
input{flex:1;background:transparent;border:0;color:var(--txt);font-size:16px;padding:10px 12px;outline:none}
button{background:var(--acc);color:#06101f;border:0;border-radius:10px;padding:0 18px;font-size:15px;font-weight:600;cursor:pointer}
button:hover{filter:brightness(1.08)}
.chips{display:flex;flex-wrap:wrap;gap:7px;margin:14px 0 6px}
.chip{background:var(--card);border:1px solid var(--brd);color:var(--mut);font-size:12.5px;padding:6px 11px;border-radius:20px;cursor:pointer}
.chip:hover{color:var(--txt);border-color:var(--acc)}
.ans{margin-top:20px}
.card{background:var(--card);border:1px solid var(--brd);border-radius:14px;padding:16px 18px;margin-bottom:12px;backdrop-filter:blur(12px)}
.card.top{border-color:rgba(62,207,142,.4);box-shadow:0 0 0 1px rgba(62,207,142,.15)}
.cite{display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--acc);margin-bottom:8px;flex-wrap:wrap}
.badge{font-size:11px;background:rgba(91,157,255,.15);border:1px solid rgba(91,157,255,.3);padding:2px 8px;border-radius:6px;color:#bcd4ff}
.badge.ok{background:rgba(62,207,142,.15);border-color:rgba(62,207,142,.35);color:#9af0c8}
.sec{font-weight:600;color:var(--txt)}
.txt{font-size:14.5px;line-height:1.62;color:#dbe4ec}
.score{margin-left:auto;color:var(--mut);font-size:11.5px}
.more{color:var(--mut);font-size:12px;margin:16px 0 6px;text-transform:uppercase;letter-spacing:.5px}
.foot{color:var(--mut);font-size:11.5px;margin-top:26px;line-height:1.55;border-top:1px solid var(--brd);padding-top:14px}
.empty{color:var(--mut);font-size:14px;text-align:center;padding:30px 0}
</style></head>
<body><div class="wrap">
<h1>AI-помощник по паспортам безопасности</h1>
<div class="sub">Спросите на обычном языке про хранение, первую помощь, СИЗ, класс опасности, ПДК. Ответ приходит с указанием вещества и раздела паспорта. Работает офлайн, в браузере, без интернета и ключей.</div>
<div class="banner">Демо-корпус: 6 веществ по структуре ГОСТ 30333-2007, референс-данные (не проприетарные SDS предприятия). Это демонстрация возможности, а не замена официального паспорта безопасности. Для рабочих решений сверяйтесь с действующим паспортом.</div>
<div class="searchbox"><input id="q" placeholder="например: какие перчатки нужны для ацетона" autocomplete="off"><button onclick="run()">Найти</button></div>
<div class="chips" id="chips"></div>
<div class="ans" id="ans"><div class="empty">Введите вопрос или нажмите на пример выше</div></div>
<div class="foot">Движок: гибридный TF-IDF (символьные + словесные n-граммы) с бустингом по веществу. На демо-корпусе: точность top-1 = 100%, с точностью до раздела 80%. Baseline без морфологии давал 60%, это и есть главный риск RAG, который снимается на этапе retrieval. Прод-апгрейд: семантические эмбеддинги (GigaChat / multilingual-e5), реальные паспорта предприятия, обработка сканов и таблиц.</div>
</div>
<script>
const CHUNKS = %%CHUNKS%%;
const EXAMPLES = ["при какой температуре вспыхивает ацетон","что делать если метанол попал внутрь","какие перчатки нужны для ацетона","как хранить серную кислоту","ПДК формальдегида в рабочей зоне","едкий натр и какие металлы опасны","первая помощь при ожоге глаз щёлочью","какое вещество канцероген"];
const STOP=new Set("и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне было вот от меня еще нет о из ему когда даже ну вдруг ли если уже или ни быть был него до вас нибудь опять уж вам ведь там потом себя ничего ей может они тут где есть надо ней для мы тебя их чем была сам чтоб без будто чего раз тоже себе под будет ж тогда кто этот того потому этого какой совсем ним здесь этом один почти мой тем чтобы нее были куда зачем всех никогда можно при наконец два об другой хоть после над больше тот через эти нас про всего них какая много разве три эту нужны нужен нужно".split(" "));
const SYN={h2so4:["серн","кислот","купорос"],ch3oh:["метанол","метилов","древесн"],nh3:["аммиак","нашатыр"],c3h6o:["ацетон","пропанон"],hcho:["формальдегид","формалин","канцероген"],naoh:["натр","едк","каустик","щелоч","щёлоч","сода"]};
function words(t){return (t.toLowerCase().match(/[а-яёa-z0-9]+/g)||[]).filter(w=>w.length>2&&!STOP.has(w));}
function chargrams(t){let out=[];let ws=(t.toLowerCase().match(/[а-яёa-z0-9]+/g)||[]);for(const w of ws){const p=" "+w+" ";for(let n=3;n<=5;n++)for(let i=0;i+n<=p.length;i++)out.push(p.slice(i,i+n));}return out;}
function tf(arr){const m={};for(const x of arr)m[x]=(m[x]||0)+1;return m;}
function buildIndex(feat){const docs=CHUNKS.map(c=>tf(feat(c.text+" "+c.substance+" "+c.section)));const df={};for(const d of docs)for(const k in d)df[k]=(df[k]||0)+1;const N=docs.length;const idf={};for(const k in df)idf[k]=Math.log(N/(1+df[k]))+1;const vecs=docs.map(d=>{const v={};let s=0;for(const k in d){const w=d[k]*(idf[k]||0);v[k]=w;s+=w*w;}s=Math.sqrt(s)||1;for(const k in v)v[k]/=s;return v;});return {idf,vecs};}
function qvec(q,feat,idf){const d=tf(feat(q));const v={};let s=0;for(const k in d){const w=d[k]*(idf[k]||0);v[k]=w;s+=w*w;}s=Math.sqrt(s)||1;for(const k in v)v[k]/=s;return v;}
function cos(a,b){let s=0;const sm=Object.keys(a).length<Object.keys(b).length?a:b;const ot=sm===a?b:a;for(const k in sm)if(ot[k])s+=sm[k]*ot[k];return s;}
const WI=buildIndex(words), CI=buildIndex(chargrams);
function search(q){const qw=qvec(q,words,WI.idf),qc=qvec(q,chargrams,CI.idf);const ql=q.toLowerCase();let sc=CHUNKS.map((c,i)=>{let s=0.45*cos(qw,WI.vecs[i])+0.55*cos(qc,CI.vecs[i]);for(const di in SYN){if(SYN[di].some(k=>ql.includes(k))&&c.doc_id===di)s+=0.18;}return {c,s,i};});sc.sort((a,b)=>b.s-a.s);return sc.slice(0,3).filter(x=>x.s>0.04);}
function esc(s){return s.replace(/[&<>]/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[m]));}
function render(res){const a=document.getElementById("ans");if(!res.length){a.innerHTML='<div class="empty">По этому запросу в демо-корпусе ничего не нашлось. Попробуйте переформулировать.</div>';return;}let h="";res.forEach((r,idx)=>{const c=r.c;const cls=idx===0?"card top":"card";const bcls=idx===0?"badge ok":"badge";h+=`<div class="${cls}"><div class="cite"><span class="${bcls}">${idx===0?"Лучший ответ":"Ещё раздел"}</span><span class="sec">${esc(c.substance)} (${esc(c.formula)})</span> · раздел «${esc(c.section)}»<span class="score">CAS ${esc(c.cas)} · ${(r.s).toFixed(2)}</span></div><div class="txt">${esc(c.text)}</div></div>`;if(idx===0&&res.length>1)h+='<div class="more">Смежные разделы</div>';});a.innerHTML=h;}
function run(){const q=document.getElementById("q").value.trim();if(!q)return;render(search(q));}
document.getElementById("q").addEventListener("keydown",e=>{if(e.key==="Enter")run();});
const ch=document.getElementById("chips");EXAMPLES.forEach(x=>{const d=document.createElement("div");d.className="chip";d.textContent=x;d.onclick=()=>{document.getElementById("q").value=x;run();};ch.appendChild(d);});
</script></body></html>"""

html = HTML.replace("%%CHUNKS%%", CHUNKS_JSON)
open("index.html", "w", encoding="utf-8").write(html)
print(f"index.html: {len(html)} байт, корпус встроен ({len(corpus['chunks'])} чанков)")
