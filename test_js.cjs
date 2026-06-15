const fs=require("fs");
const html=fs.readFileSync("index.html","utf8");
// Pull the corpus and the script body, eval in a sandbox-ish way
const CHUNKS=JSON.parse(html.match(/const CHUNKS = (\[.*?\]);/s)[1]);
// replicate engine
const STOP=new Set("и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне было вот от меня еще нет о из ему когда даже ну вдруг ли если уже или ни быть был него до вас нибудь опять уж вам ведь там потом себя ничего ей может они тут где есть надо ней для мы тебя их чем была сам чтоб без будто чего раз тоже себе под будет ж тогда кто этот того потому этого какой совсем ним здесь этом один почти мой тем чтобы нее были куда зачем всех никогда можно при наконец два об другой хоть после над больше тот через эти нас про всего них какая много разве три эту нужны нужен нужно".split(" "));
const SYN={h2so4:["серн","кислот","купорос"],ch3oh:["метанол","метилов","древесн"],nh3:["аммиак","нашатыр"],c3h6o:["ацетон","пропанон"],hcho:["формальдегид","формалин","канцероген"],naoh:["натр","едк","каустик","щелоч","щёлоч","сода"]};
function words(t){return (t.toLowerCase().match(/[а-яёa-z0-9]+/g)||[]).filter(w=>w.length>2&&!STOP.has(w));}
function chargrams(t){let out=[];let ws=(t.toLowerCase().match(/[а-яёa-z0-9]+/g)||[]);for(const w of ws){const p=" "+w+" ";for(let n=3;n<=5;n++)for(let i=0;i+n<=p.length;i++)out.push(p.slice(i,i+n));}return out;}
function tf(arr){const m={};for(const x of arr)m[x]=(m[x]||0)+1;return m;}
function buildIndex(feat){const docs=CHUNKS.map(c=>tf(feat(c.text+" "+c.substance+" "+c.section)));const df={};for(const d of docs)for(const k in d)df[k]=(df[k]||0)+1;const N=docs.length;const idf={};for(const k in df)idf[k]=Math.log(N/(1+df[k]))+1;const vecs=docs.map(d=>{const v={};let s=0;for(const k in d){const w=d[k]*(idf[k]||0);v[k]=w;s+=w*w;}s=Math.sqrt(s)||1;for(const k in v)v[k]/=s;return v;});return {idf,vecs};}
function qvec(q,feat,idf){const d=tf(feat(q));const v={};let s=0;for(const k in d){const w=d[k]*(idf[k]||0);v[k]=w;s+=w*w;}s=Math.sqrt(s)||1;for(const k in v)v[k]/=s;return v;}
function cos(a,b){let s=0;const sm=Object.keys(a).length<Object.keys(b).length?a:b;const ot=sm===a?b:a;for(const k in sm)if(ot[k])s+=sm[k]*ot[k];return s;}
const WI=buildIndex(words),CI=buildIndex(chargrams);
function search(q){const qw=qvec(q,words,WI.idf),qc=qvec(q,chargrams,CI.idf);const ql=q.toLowerCase();let sc=CHUNKS.map((c,i)=>{let s=0.45*cos(qw,WI.vecs[i])+0.55*cos(qc,CI.vecs[i]);for(const di in SYN){if(SYN[di].some(k=>ql.includes(k))&&c.doc_id===di)s+=0.18;}return {c,s};});sc.sort((a,b)=>b.s-a.s);return sc.slice(0,3);}
const TESTS=[["при какой температуре вспыхивает ацетон","c3h6o"],["что делать если метанол попал внутрь, антидот","ch3oh"],["какие перчатки нужны для работы с ацетоном","c3h6o"],["как хранить серную кислоту рядом с чем нельзя","h2so4"],["ПДК формальдегида в воздухе рабочей зоны","hcho"],["едкий натр выделяет водород с какими металлами","naoh"],["первая помощь при ожоге глаз щёлочью","naoh"],["какое вещество канцероген","hcho"],["чем опасен аммиак при вдыхании","nh3"],["куда приливать кислоту в воду или воду в кислоту","h2so4"]];
let hit=0;for(const [q,d] of TESTS){const r=search(q);const ok=r[0].c.doc_id===d;hit+=ok;console.log((ok?"OK  ":"MISS")+" "+q.slice(0,42).padEnd(42)+" -> "+r[0].c.substance+" / "+r[0].c.section);}
console.log("JS top-1: "+hit+"/"+TESTS.length+" = "+Math.round(hit/TESTS.length*100)+"%");
