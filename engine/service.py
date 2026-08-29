# -*- coding: utf-8 -*-
"""
Деплоимый сервис AI-помощника по промышленной безопасности.
Эндпоинты: /health /search /ask /plant /substance /metrics.
Бэкенды эмбеддингов/генерации сменные (env): on-prem Ollama по умолчанию для прода,
extractive (без модели) как безопасный fallback. Retrieval — гибридный лексический.
"""
import os, json, io, csv, html as _html
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from retriever import HybridRetriever, SemanticRetriever
from cache import SemanticCache
from backends import get_llm_backend
import compat, ghs_map, hygiene, baseline, registry, quiz, sanpin, pubchem, verification, physchem, sanpin_env, transport, answer_review, gost_sections, normative, waste
import ppe, warehouse, inspection, waste_calc, dispatch, shift_alert  # расширение: СИЗ / карта склада / инспектор / класс отхода / диспетчер / реакция на превышение
try:
    import segno  # QR (pure-python); если нет — /qr отключаем
except ImportError:
    segno = None
try:
    import rd_zone  # грузит data/rd_ahov.json; если нет — эндпоинт /zone отключаем
except (FileNotFoundError, OSError):
    rd_zone = None

app = FastAPI(title="HEFEST — SDS Safety Assistant", version="1.0")
# CORS: UI (emergency.html) может открываться как file:// или с другого порта.
# Внутренний on-prem инструмент -> allow-all допустимо (контур закрыт).
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- Опциональная аутентификация по API-ключу (defense-in-depth) ---------------------------------
# По умолчанию ВЫКЛ (пусто) — для демо и закрытого КИИ-контура (сеть изолирована). Включается заданием
# API_KEY: тогда все запросы, кроме /health и статики UI, требуют заголовок X-API-Key. Это СТОПГАП:
# основная аутентификация на проде — обратный прокси с AD/LDAP предприятия (см. DEPLOY.md).
API_KEY = os.getenv("API_KEY", "")
_AUTH_EXEMPT = ("/health", "/docs", "/openapi.json", "/redoc", "/assets", "/doc/")

@app.middleware("http")
async def _api_key_guard(request: Request, call_next):
    if API_KEY:
        path = request.url.path
        exempt = (path == "/" or path.endswith(".html")
                  or any(path == p or path.startswith(p) for p in _AUTH_EXEMPT))
        if not exempt and request.headers.get("X-API-Key") != API_KEY:
            return JSONResponse({"error": "требуется X-API-Key"}, status_code=401)
    return await call_next(request)

# --- Отдача UI самим сервисом: одна точка входа (один URL для пользователя) ------------------------
_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
_UI_PAGES = {"home", "substance", "emergency", "label", "registry", "quiz", "guide", "safety", "console", "readiness", "reviews", "gost",
             "ppe", "warehouse", "inspection", "waste", "dispatch", "shift"}
if os.path.isdir(os.path.join(_ROOT, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(_ROOT, "assets")), name="assets")

# no-cache на HTML: браузер всегда берёт свежую версию (иначе показывает старый UI из кэша,
# т.к. FileResponse шлёт etag/last-modified, но браузер кэширует эвристически без перезапроса).
_NOCACHE = {"Cache-Control": "no-cache, must-revalidate"}

@app.get("/", response_class=HTMLResponse)
def ui_root():
    fp = os.path.join(_ROOT, "home.html")
    return FileResponse(fp, headers=_NOCACHE) if os.path.isfile(fp) else HTMLResponse("UI не найден", status_code=404)

@app.get("/{page}.html", response_class=HTMLResponse)
def ui_page(page: str):
    if page not in _UI_PAGES:  # whitelist -> без обхода путей (../)
        return HTMLResponse("страница не найдена", status_code=404)
    fp = os.path.join(_ROOT, page + ".html")
    return FileResponse(fp, headers=_NOCACHE) if os.path.isfile(fp) else HTMLResponse("страница не найдена", status_code=404)

# --- Отдача документов (.md) человеку: рендерим в читаемую страницу, а не сырой текст -------------
# Раньше футер ссылался на MARKET.md/DEMO.md/WORKLOG.md напрямую -> 404 (сервер их не отдавал).
# Теперь /doc/<имя> рендерит любой .md из корня и docs/ (whitelist по факту наличия, без обхода путей).
_DOC_DIRS = [_ROOT, os.path.join(_ROOT, "docs")]

def _doc_index():
    idx = {}
    for d in _DOC_DIRS:
        try:
            for fn in os.listdir(d):
                if fn.lower().endswith(".md"):
                    idx.setdefault(fn, os.path.join(d, fn))
        except OSError:
            pass
    return idx

_DOC_PAGE = """<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>:root{{--bg:#0f1419;--panel:#1a2230;--line:#2b3647;--txt:#eef2f7;--muted:#9aa6b4;--accent:#5b9dff;--orange:#f9a23b}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--txt);
font:16px/1.7 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:820px;margin:0 auto;padding:28px 20px 80px}}
a.back{{display:inline-block;margin-bottom:18px;color:var(--muted);text-decoration:none;font-size:15px}}
a.back:hover{{color:var(--accent)}}
.doc{{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:30px 34px}}
.doc h1{{font-size:26px;margin:.2em 0 .6em;line-height:1.25}}
.doc h2{{font-size:20px;margin:1.4em 0 .5em;border-top:1px solid var(--line);padding-top:1em}}
.doc h3{{font-size:17px;margin:1.2em 0 .4em;color:var(--orange)}}
.doc a{{color:var(--accent)}}.doc code{{background:#0d1117;border:1px solid var(--line);border-radius:6px;padding:1px 6px;font-size:.9em}}
.doc pre{{background:#0d1117;border:1px solid var(--line);border-radius:10px;padding:14px;overflow:auto}}
.doc pre code{{border:0;padding:0;font-size:11px;line-height:1.4;white-space:pre}}.doc blockquote{{margin:1em 0;padding:.4em 1.1em;border-left:3px solid var(--accent);color:var(--muted)}}
.doc table{{border-collapse:collapse;width:100%;margin:1em 0;font-size:14.5px}}
.doc th,.doc td{{border:1px solid var(--line);padding:8px 11px;text-align:left;vertical-align:top}}
.doc th{{background:#0d1117}}.doc img{{max-width:100%}}.doc li{{margin:.25em 0}}
</style></head><body><div class="wrap"><a class="back" href="/home.html">← на главную</a>
<div class="doc">{body}</div></div></body></html>"""

@app.get("/doc/{name}", response_class=HTMLResponse)
def ui_doc(name: str):
    fp = _doc_index().get(name) or _doc_index().get(name + ".md")
    if not fp or not os.path.isfile(fp):
        return HTMLResponse("<h2>Документ не найден</h2>", status_code=404)
    text = open(fp, encoding="utf-8").read()
    try:
        import markdown as _mdlib
        body = _mdlib.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    except Exception:
        body = "<pre>" + _html.escape(text) + "</pre>"   # фолбэк: всё равно отдаём читаемо
    return HTMLResponse(_DOC_PAGE.format(title=_html.escape(name), body=body))

# Retrieval-бэкенд по env: semantic (bge-m3 + плант-скоуп, прод on-prem) | lexical (офлайн-дефолт).
# Если индекс embeddings.npy не построен — честный фолбэк на лексику, сервис не падает.
RETRIEVER = os.getenv("RETRIEVER", "lexical")  # lexical | semantic | qdrant
try:
    if RETRIEVER == "qdrant":
        from qdrant_index import QdrantRetriever
        R = QdrantRetriever()
    elif RETRIEVER == "semantic":
        R = SemanticRetriever()
    else:
        R = HybridRetriever()
except FileNotFoundError:
    print("[service] embeddings.npy не найден -> фолбэк на лексический retriever "
          "(запусти build_semantic_index.py для семантики)")
    RETRIEVER = "lexical"; R = HybridRetriever()

# Опциональный реранк (только поверх семантики): RERANK=1, RERANK_BACKEND=crossencoder|llm.
# crossencoder = bge-reranker-v2-m3 (быстрый, MPS); llm = Ollama (air-gapped, медленнее).
# Отказоустойчиво: не загрузился -> сервис работает без реранка.
RERANK_BACKEND = os.getenv("RERANK_BACKEND", "crossencoder")
if RETRIEVER == "semantic" and os.getenv("RERANK", "0") == "1":
    try:
        if RERANK_BACKEND == "llm":
            from reranker_llm import get_reranker
        else:
            from reranker_model import get_reranker
        R.reranker = get_reranker(); R.rerank_n = int(os.getenv("RERANK_N", "20"))
        print(f"[service] реранк включён: {RERANK_BACKEND} (N={R.rerank_n})")
    except Exception as e:
        print(f"[service] реранк не загружен ({e}) -> работаю без реранка")
        RERANK_BACKEND = None
else:
    RERANK_BACKEND = None
LLM = get_llm_backend(os.getenv("LLM_BACKEND", "extractive"),
                      **({"model": os.getenv("OLLAMA_LLM","qwen2.5:7b")} if os.getenv("LLM_BACKEND")=="ollama" else {}))
CACHE = SemanticCache()  # в проде embed_fn = Ollama bge-m3 для L3

SUBS = {s["name"].lower(): s for s in R.subs}

# Аварийный слой (АХОВ): ООН-номер, класс ДОПОГ. needs_review — сверить по офиц. таблице.
_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
try:
    AHOV = json.load(open(os.path.join(_DATA, "ahov_cards.json"), encoding="utf-8"))
except FileNotFoundError:
    AHOV = {"cards": {}, "_meta": {"disclaimer": "ahov_cards.json не найден"}}

# IDLH (острый порог, NIOSH, public domain) — по CAS. needs_review: сверять с cdc.gov/niosh/idlh.
def _load_json(fn, default):
    try:
        return json.load(open(os.path.join(_DATA, fn), encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return default  # файл отсутствует или читается в момент записи фонового фетчера
IDLH = _load_json("idlh.json", {})
# Расстояния эвакуации/изоляции ERG-2024 + ООН/ДОПОГ (ориентир первого реагирования). needs_review.
ERG = _load_json("erg_ahov.json", {"cards": {}}).get("cards", {})
ERG_META = _load_json("erg_ahov.json", {}).get("_meta", {})
# Эталонная GHS-классификация PubChem (NIH, public domain) по CAS — для сверки/обогащения знаков.
PUBCHEM = _load_json("pubchem_ghs.json", {})
# Русские синонимы (Wikidata, CC0) — для распознавания запросов.
SYN = _load_json("synonyms.json", {})
SYN_INDEX = {}  # синоним_lower -> каноническое имя_lower
for _canon, _rec in SYN.items():
    if _canon == "_meta":
        continue
    for _s in _rec.get("synonyms", []):
        SYN_INDEX.setdefault(_s.lower().strip(), _canon)

def _resolve_sub(name):
    """Вещество по имени или синониму (Wikidata). Возвращает (объект, разрешённое_имя) или (None,None)."""
    key = (name or "").lower().strip()
    if key in SUBS:
        return SUBS[key], key
    canon = SYN_INDEX.get(key)
    if canon and canon in SUBS:
        return SUBS[canon], canon
    return None, None

def _idlh_for(s):
    """IDLH-запись по CAS вещества (или None)."""
    cas = (s or {}).get("cas")
    rec = IDLH.get(cas) if cas else None
    return rec if (rec and rec.get("idlh") is not None) else None

def _physchem_for(s):
    """Физико-химические свойства по CAS (PubChem, public domain) или None."""
    return physchem.for_cas((s or {}).get("cas"))

def _verify_status(s):
    """Статус экспертной верификации вещества (+ алгоритмическая confidence/tier как контекст)."""
    if not s:
        return None
    v = verification.status_for(s.get("name"))
    v["confidence"] = s.get("confidence")      # машинная уверенность (другое, чем подпись)
    v["source_tier"] = s.get("source_tier")
    return v

class Ask(BaseModel):
    question: str
    plant: str | None = None
    substance: str | None = None        # явно выбранное вещество (после уточнения неоднозначности)

# Порог неоднозначности: если 2+ РАЗНЫХ вещества в выдаче с близким score (разрыв меньше) — спрашиваем,
# а не угадываем. Цена ошибки = здоровье: лучше уточнить вещество, чем смешать ответ из разных паспортов.
CLARIFY_DELTA = float(os.getenv("CLARIFY_DELTA", "0.04"))

def _distinct_candidates(res, limit=4):
    """Из выдачи — РАЗНЫЕ вещества с их лучшим score (для уточнения и мягкого подтверждения).
    Дедуп по CAS: «ацетон» и «пропан-2-он (ацетон)» — одно вещество (CAS 67-64-1), не предлагаем дважды."""
    seen_name, seen_cas, out = set(), set(), []
    for c, sc in res:
        nm = c.get("substance")
        if not nm or nm in seen_name:
            continue
        cas = c.get("cas")
        if cas and cas in seen_cas:        # тот же CAS уже есть под другим именем -> дубль
            continue
        seen_name.add(nm)
        if cas:
            seen_cas.add(cas)
        out.append({"substance": nm, "score": round(float(sc), 3), "cas": cas,
                    "verification": verification.status_for(nm)["status"]})
    return out[:limit]


# Индекс имён для гарда «слишком общий запрос» (подстрока во многих веществах).
_NAME_LIST = [s["name"] for s in SUBS.values()]

def _too_generic(q):
    """Один короткий токен, НЕ точное имя, но подстрока многих веществ ('водород', 'хлорид').
    Возвращает (count, suggestions) если запрос слишком общий, иначе None. Защита от молчаливого
    ответа про произвольное (часто опасное) вещество — лучше попросить уточнить."""
    t = (q or "").strip().lower()
    if not t or " " in t or len(t) < 3:
        return None
    if t in SUBS or SYN_INDEX.get(t):     # точное имя/синоним -> якорится отдельно, не общий
        return None
    matches = [n for n in _NAME_LIST if t in n.lower()]
    if len(matches) < 8:                  # мало совпадений -> не «общий», обычный retrieval
        return None
    suggestions = sorted(matches, key=len)[:6]   # короткие имена = обычно базовые вещества
    return len(matches), suggestions


# Детектор упоминания вещества в вопросе, устойчивый к склонению (фикс ложного отказа на фразах
# вроде «как хранить серную кислоту»: лексический ретривер не сводит «серную кислоту» -> «серная кислота»).
import re as _re
_WORD = _re.compile(r"[а-яёa-z0-9]+")
_QSTOP = {"при", "для", "как", "что", "чем", "это", "или", "под", "над", "после", "перед", "если"}

def _name_stems(name):
    """Значимые слова имени (len>=4, напр. «хлор», «азот»), без стоп-слов — полностью, не урезая.
    Сравнение со словами вопроса идёт по общему префиксу с поправкой на склонение (см. _root_match)."""
    return [w for w in _WORD.findall(name.lower()) if len(w) >= 4 and w not in _QSTOP]

# Предрасчёт: (имя, стеммы) по всем веществам — для детекции упоминания.
_SUB_STEMS = [(s["name"], _name_stems(s["name"])) for s in SUBS.values()]

def _common_prefix_len(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n

def _root_match(stem, qword):
    """Совпадение корня имени со словом вопроса с поправкой на склонение. Возвращает «силу»
    совпадения (длину общего корня) или 0. Ключ к различению пересекающихся имён:
    требуем, чтобы у ОБОИХ слов «хвост» за общим корнем был коротким окончанием (<=3).
    Тогда «хлором» совпадает с «хлор» (хвосты 2/0), но НЕ с «хлороформ» (хвост 4);
    «бензола» — с «бензол» (1/0), но НЕ с «бензилметилбензол» (хвост 13);
    «серную» — с «серная» (2/2). Это и есть граница между склонением и другим веществом."""
    cp = _common_prefix_len(stem, qword)
    if cp < 4:
        return 0
    if (len(stem) - cp) > 3 or (len(qword) - cp) > 3:
        return 0                           # длинный хвост = это другое слово/вещество, не склонение
    return cp

def _mention_scope(q):
    """Если в вопросе ОДНОЗНАЧНО упомянуто одно вещество (все корни его имени совпали со словами
    вопроса с поправкой на склонение) — вернуть его имя, иначе None. Кандидаты ранжируются по
    качеству совпадения (суммарная длина корней), затем по числу корней (специфичность). При ничьей
    качества у двух кандидатов -> None (пусть отработает обычный flow/уточнение). Цена ошибки=здоровье."""
    qwords = [w for w in _WORD.findall((q or "").lower()) if len(w) >= 4]
    if not qwords:
        return None
    scored = []
    for name, stems in _SUB_STEMS:
        if not stems:
            continue
        total, ok = 0, True
        for st in stems:
            best = max((_root_match(st, w) for w in qwords), default=0)
            if best == 0:                  # этот корень имени в вопросе не упомянут
                ok = False
                break
            total += best
        if ok:
            scored.append((name, total, len(stems)))
    if not scored:
        return None
    scored.sort(key=lambda x: (-x[1], -x[2]))
    if len(scored) >= 2 and scored[0][1] == scored[1][1]:   # одинаково сильное совпадение -> неоднозначно
        return None
    return scored[0][0]

@app.get("/health")
def health():
    return {"ok": True, "substances": len(R.subs), "chunks": len(R.chunks),
            "plants": len(R.plants), "retriever": RETRIEVER, "rerank": RERANK_BACKEND,
            "llm_backend": os.getenv("LLM_BACKEND","extractive")}

@app.get("/search")
def search(q: str = Query(...), k: int = 3):
    res = R.query(q, k=k)
    hygiene.audit("search", q, {"top": res[0][0]["substance"] if res else None})
    return [{"substance": c["substance"], "section": c["section"], "score": round(sc,3),
             "text": c["text"], "citation": c["citation"], "tier": c.get("source_tier"),
             "confidence": c.get("confidence"),
             "verification": verification.status_for(c["substance"])["status"]} for c, sc in res]

# Порог отказа: если лучший retrieval-score ниже — НЕ генерируем, а честно отказываем.
# Безопасность: лучше отправить к паспорту, чем выдумать (цена ошибки = здоровье).
# Калибруется на eval конкретного завода; дефолт по нашему корпусу (реальные 0.66+, шум 0.43-0.53).
# Порог зависит от ретривера: у косинуса (semantic/qdrant) распределение score ниже, чем у
# лексического гибрида (0.30·word+0.40·char+0.30·bm25). Дефолт под ретривер; калибруется eval'ом завода.
_ABSTAIN_DEFAULT = {"semantic": "0.55", "qdrant": "0.55"}.get(RETRIEVER, "0.62")
ABSTAIN_THRESHOLD = float(os.getenv("ABSTAIN_THRESHOLD", _ABSTAIN_DEFAULT))
_REFUSAL = ("Недостаточно оснований в загруженных паспортах безопасности, чтобы ответить уверенно. "
            "Обратитесь к действующему паспорту безопасности (ГОСТ 30333) или специалисту по ОТ/ПБ. "
            "Система не выдумывает ответ, когда нет подтверждённого источника.")

@app.post("/ask")
def ask(a: Ask):
    # Retrieval ВСЕГДА (дешёвый) -> кэшируем только дорогую генерацию. Так top_score/verification
    # консистентны и для кэш-хита, и для отказа.
    chosen = None
    auto_chosen = False
    if a.substance:                      # пользователь уже выбрал вещество (разрешил неоднозначность)
        cs, _ = _resolve_sub(a.substance)
        chosen = cs["name"] if cs else a.substance
        scope = {chosen}
    else:
        scope = R._plant_scope(a.plant.lower()) if a.plant else None
        # Безопасность: если ВЕСЬ запрос — точное имя/синоним вещества («хлор»), якорим на него,
        # как это делает /substance. Иначе чистый retrieval может ответить про другое вещество
        # («хлор» -> «хлор диоксид»). Вопросы-предложения сюда не попадают (нет точного совпадения).
        if not a.plant:
            exact, _ = _resolve_sub(a.question)
            if exact:
                chosen = exact["name"]
                scope = {chosen}
                auto_chosen = True       # распознано по точному совпадению, не выбрано вручную
            else:
                # Гард: одиночное общее слово ('водород', 'хлорид') -> не отвечаем про произвольное
                # вещество, а просим уточнить (с подсказками). Цена ошибки = здоровье.
                gen = _too_generic(a.question)
                if gen:
                    cnt, sugg = gen
                    cands = [{"substance": n, "score": None,
                              "verification": verification.status_for(n)["status"]} for n in sugg]
                    hygiene.audit("ask", a.question, {"too_generic": True, "matches": cnt})
                    return {"clarify": True, "too_generic": True, "candidates": cands,
                            "abstained": False, "match_count": cnt, "question": a.question,
                            "note": f"«{a.question.strip()}» — слишком общий запрос: встречается в "
                                    f"{cnt} веществах базы. Уточните конкретное вещество."}
                # Упоминание вещества в склонённой форме («...серную кислоту») — лексика его теряет.
                # Если однозначно -> мягко скоупим, чтобы не отказать на валидном вопросе.
                ment = _mention_scope(a.question)
                if ment:
                    chosen = ment
                    scope = {chosen}
                    auto_chosen = True
    if chosen:
        # Вещество зафиксировано -> берём БОЛЬШОЙ пул (scope лишь мягко бустит, не фильтрует жёстко)
        # и оставляем только фрагменты выбранного вещества. НЕ подменяем другим: если у выбранного
        # нет фрагментов — пусть честный отказ, а не ответ из чужого паспорта (цена ошибки = здоровье).
        pool = R.query(a.question, k=200, scope_substances=scope)
        res = [(c, sc) for c, sc in pool if c.get("substance") == chosen][:3]
    else:
        res = R.query(a.question, k=3, scope_substances=scope)
    passages = [c for c, _ in res]
    top_score = round(float(res[0][1]), 3) if res else 0.0
    # Гейт отказа. Если вещество ЗАФИКСИРОВАНО (chosen: выбрано вручную / заякорено по точному имени /
    # однозначно упомянуто), выдача строго из его паспорта и человек видит первичку — абсолютный порог
    # снимаем (иначе ложный отказ на валидном вопросе вроде «как хранить серную кислоту», score 0.33).
    # Иначе (вещество не определено) — обычный порог, чтобы не выдумать ответ из шумной выдачи.
    eff_thr = 0.0 if chosen else ABSTAIN_THRESHOLD
    if not passages or top_score < eff_thr:
        hygiene.audit("ask", a.question, {"plant": a.plant, "abstained": True, "top_score": top_score})
        return {"answer": _REFUSAL, "abstained": True, "cached": False,
                "top_score": top_score, "threshold": eff_thr, "sources": []}
    # Уточнение неоднозначности: если вещество не выбрано и 2+ РАЗНЫХ вещества идут вплотную — спрашиваем.
    cands = _distinct_candidates(res)
    if not chosen and len(cands) >= 2 and (cands[0]["score"] - cands[1]["score"]) < CLARIFY_DELTA:
        hygiene.audit("ask", a.question, {"plant": a.plant, "clarify": True,
                      "candidates": [c["substance"] for c in cands]})
        return {"clarify": True, "candidates": cands, "abstained": False,
                "top_score": top_score, "threshold": ABSTAIN_THRESHOLD,
                "question": a.question, "plant": a.plant}
    ckey = (chosen + " :: " if chosen else "") + a.question
    cached = CACHE.get(ckey)
    if cached is not None:
        answer, was_cached = cached, True
    else:
        answer = LLM.generate(a.question, passages); CACHE.put(ckey, answer); was_cached = False
    top = passages[0]
    s, _ = _resolve_sub(top.get("substance", ""))
    hygiene.audit("ask", a.question, {"plant": a.plant, "top": top["substance"],
                  "abstained": False, "top_score": top_score, "cached": was_cached})
    # Первичка для СВЕРКИ человеком: точный текст найденного раздела + провенанс (документ/раздел/score).
    # Доверие: ответ — удобство, паспорт — истина; человек всегда видит исходный фрагмент и судит сам.
    src_passages = [{"substance": c.get("substance"), "section": c.get("section"),
                     "text": c.get("text"), "citation": c.get("citation"),
                     "score": round(float(sc), 3), "tier": c.get("source_tier"),
                     "verification": verification.status_for(c.get("substance"))["status"]}
                    for c, sc in res]
    return {"answer": answer, "abstained": False, "cached": was_cached,
            "top_score": top_score, "threshold": ABSTAIN_THRESHOLD,
            "sources": [p["citation"] for p in passages],
            "passages": src_passages,
            "top_substance": top.get("substance"),
            "top_confidence": top.get("confidence"),
            "candidates": cands,          # распознанное вещество + альтернативы (мягкое подтверждение)
            "chosen": chosen,             # вещество выбрано (вручную) или распознано по точному имени
            "auto_chosen": auto_chosen,   # True = заякорено по точному совпадению запроса с именем
            "verification": _verify_status(s) if s else None}

@app.get("/plant/{name}")
def plant(name: str):
    p = R._plant_scope(name.lower())
    key = None
    for trig, k in R.plant_triggers.items():
        if trig in name.lower(): key = k; break
    prof = R.plants.get(key) if key else None
    if not prof:
        return _plant_missing(name)
    subs = []
    for sn in prof.get("matched_substances", []):
        s = SUBS.get(sn.lower(), {})
        subs.append({"name": sn, "hazard_class": s.get("hazard_class"),
                     "pdk": s.get("pdk_mgm3"), "cas": s.get("cas")})
    subs.sort(key=lambda x: str(x["hazard_class"] or "9"))
    return {"plant": prof["plant"], "inn": prof.get("inn"), "products": prof.get("products"),
            "hazard_substances": subs, "unmatched": prof.get("unmatched_substances")}

def _assemble(s):
    """Собирает полную карточку вещества (все слои данных + карта 16 разделов ГОСТ).
    Используется и /substance, и дашбордом соответствия — единый код = единый результат."""
    # Типовое руководство по группе для недостающих оперативных полей (явно помечено).
    out = {**s, "guidance": baseline.baseline_for(s)}
    idlh = _idlh_for(s)
    if idlh:
        out["idlh"] = idlh            # острый порог (NIOSH), needs_review
    sp = sanpin.summary(s)
    if sp and sp["flags"]:
        out["sanpin"] = sp            # особые отметки СанПиН (О/К/А/Ф/кожа)
    pc = _pubchem_for(s)
    if pc:                            # эталонные H-коды + сверка пиктограмм (PubChem)
        our = [p["code"] for p in ghs_map.ghs_profile(s).get("pictograms", [])]
        out["pubchem"] = {"pictograms": pc.get("pictograms"), "signal_word": pc.get("signal_word"),
                          "h_codes": pubchem.decode_hcodes(pc.get("h_codes")),
                          "crosscheck": pubchem.crosscheck(our, pc.get("pictograms"))}
    ph = _physchem_for(s)
    if ph:                            # физхимия (PubChem): темп. вспышки, НКПР/ВКПР, давление пара и т.д.
        out["physchem"] = ph
    env = sanpin_env.for_substance(s.get("cas"), s.get("name"))
    if env:                           # экологические ПДК (СанПиН): атмосфера населённых мест / вода
        out["sanpin_env"] = env
    tr = transport.for_cas(s.get("cas"))
    if tr:                            # транспортная идентификация (ООН/ERG/метка) из PubChem
        out["transport"] = tr
    if SYN.get(s["name"].lower()):
        out["synonyms"] = SYN[s["name"].lower()]["synonyms"]
    w = waste.for_substance(s)
    if w:                             # раздел 13: типовые меры удаления отходов + рамка ФККО/89-ФЗ
        out["waste"] = w
    out["verification"] = _verify_status(s)   # экспертная подпись (по умолчанию needs_review)
    out["gost_map"] = gost_sections.coverage_for(out)  # карта 16 разделов ГОСТ 30333: чем закрыт раздел
    return out


@app.get("/substance/{name}")
def substance(name: str):
    s, resolved = _resolve_sub(name)
    if not s: return {"error": "вещество не найдено"}
    out = _assemble(s)
    if name.lower().strip() != s["name"].lower():
        out["resolved_from"] = name   # запрос распознан по синониму
    return out


# Дашборд соответствия ГОСТ 30333: покрытие 16 разделов по всей номенклатуре (кэш).
_GOST_AGG = None

def _gost_aggregate():
    global _GOST_AGG
    if _GOST_AGG is not None:
        return _GOST_AGG
    per_section = {sec["n"]: {"n": sec["n"], "title": sec["title"], "short": sec["short"],
                              "full": 0, "partial": 0, "corpus": 0, "gap": 0, "na": 0}
                   for sec in gost_sections.SECTIONS}
    n_subs = 0
    for s in SUBS.values():
        n_subs += 1
        cov = gost_sections.coverage_for(_assemble(s))
        for sec in cov["sections"]:
            per_section[sec["n"]][sec["status"]] += 1
    _GOST_AGG = {
        "substances": n_subs,
        "sections": list(per_section.values()),
        "title_needs_review": gost_sections.TITLE_NEEDS_REVIEW,
        "standard": "ГОСТ 30333-2022",
    }
    return _GOST_AGG


@app.get("/gost/summary")
def gost_summary():
    """Агрегат покрытия 16 разделов ГОСТ 30333 по всей базе веществ."""
    return _gost_aggregate()


@app.get("/gost/{name}")
def gost_substance(name: str):
    """Карта 16 разделов для одного вещества (для инлайн-блока и проверки)."""
    s, _ = _resolve_sub(name)
    if not s: return {"error": "вещество не найдено"}
    return {"name": s["name"], "gost_map": gost_sections.coverage_for(_assemble(s))}


@app.get("/normative")
def normative_register():
    """Реестр нормативки (ГОСТ/СанПиН/РД/ФЗ): версии и статус + отчёт аудита устаревших ссылок."""
    audit = _load_json("version_audit.json", None)
    return {"register": normative.REGISTER, "summary": normative.summary_counts(),
            "audit": audit}


@app.get("/compliance/selfcheck")
def compliance_selfcheck():
    """ФЗ-контур: само-проверка позы соответствия (152-ФЗ / 187-ФЗ КИИ / 116-ФЗ).
    Честный снимок состояния — не обещания, а факты конфигурации на рантайме."""
    llm = os.getenv("LLM_BACKEND", "extractive")
    log_path = os.path.join(_DATA_DIR, "audit_log.jsonl") if "_DATA_DIR" in globals() else \
               os.path.join(os.path.dirname(__file__), "..", "data", "audit_log.jsonl")
    log_exists = os.path.isfile(log_path)
    log_size = os.path.getsize(log_path) if log_exists else 0
    checks = [
        {"id": "offline_runtime", "law": "187-ФЗ (КИИ), 152-ФЗ",
         "title": "Офлайн-рантайм без внешних вызовов",
         "ok": True,
         "detail": f"LLM-бэкенд «{llm}» работает локально (ollama/extractive). "
                   "Внешние обращения — только build-time фетчи (PubChem), не на рантайме."},
        {"id": "access_control", "law": "152-ФЗ",
         "title": "Контроль доступа (ключ X-API-Key)",
         "ok": bool(API_KEY),
         "detail": "API_KEY задан — доступ закрыт ключом." if API_KEY
                   else "API_KEY не задан (демо-режим). Для прод-контура — выставить API_KEY."},
        {"id": "audit_trail", "law": "187-ФЗ, 152-ФЗ",
         "title": "Журнал доступа (append-only, на диске, с ротацией)",
         "ok": log_exists,
         "detail": (f"audit_log.jsonl: {log_size} байт, ротация по поколениям." if log_exists
                    else "Журнал ещё пуст — появится при первом запросе.")},
        {"id": "provenance", "law": "общий принцип безопасности",
         "title": "Провенанс каждого значения + needs_review",
         "ok": True,
         "detail": "Каждое регуляторное значение — с источником; данные «требуют проверки» до подписи эксперта."},
        {"id": "legal_sourcing", "law": "ст. 1259 п.6 ГК РФ",
         "title": "Юридически чистые источники данных",
         "ok": True,
         "detail": "Только официальные акты РФ (не охраняются АП) и public domain (PubChem/NIH). "
                   "Источники с ограничительной лицензией (ICSC/IARC) сознательно не используются."},
        {"id": "normative_currency", "law": "актуальность нормативки",
         "title": "Реестр версий нормативки + аудит устаревших ссылок",
         "ok": True,
         "detail": "Модуль normative.py отслеживает действующие редакции; audit_versions.py находит устаревшее."},
    ]
    return {"checks": checks,
            "passed": sum(1 for c in checks if c["ok"]),
            "total": len(checks),
            "note": "Само-проверка отражает текущую конфигурацию рантайма, а не гарантию. "
                    "Финальная аттестация по 187-ФЗ/152-ФЗ — на стороне заказчика и его ИБ-службы."}

class Verify(BaseModel):
    substance: str
    status: str                 # verified | rejected | needs_review
    by: str                     # ФИО/должность ответственного — обязательно для verified/rejected
    role: str | None = None     # напр. «инженер по ОТ/ПБ», «эколог»
    note: str | None = None
    fields: list[str] | None = None  # какие поля подтверждены (pdk/класс/первая помощь...)

@app.post("/verify")
def verify(v: Verify):
    """Поставить/снять экспертную подпись на вещество (кто и когда — фиксируется). Tier-0 доверия."""
    s, _ = _resolve_sub(v.substance)
    if not s:
        return {"error": "вещество не найдено", "substance": v.substance}
    ok, res = verification.mark(s["name"], v.status, by=v.by, role=v.role, note=v.note, fields=v.fields)
    if not ok:
        return {"error": res}
    hygiene.audit("verify", s["name"], {"status": v.status, "by": v.by, "role": v.role})
    return {"substance": s["name"], "verification": verification.status_for(s["name"]), "saved": True}

@app.get("/verification")
def verification_summary():
    """Сводка готовности: сколько веществ подписано экспертом vs требует проверки (для дашборда)."""
    return {**verification.summary(total_substances=len(R.subs)),
            "records": verification.records(),
            "meta": verification._load().get("_meta")}

@app.get("/verification/{name}")
def verification_one(name: str):
    s, _ = _resolve_sub(name)
    if not s: return {"error": "вещество не найдено"}
    return {"substance": s["name"], **(_verify_status(s) or {})}

class AnswerReview(BaseModel):
    question: str
    verdict: str                          # correct | incorrect | partial
    by: str                               # ФИО/должность — обязательно (подпись)
    answer: str | None = None
    top_score: float | None = None
    data_ok: bool | None = None           # данные соответствуют первичке
    useful: bool | None = None            # ответ полезен
    sources: list[dict] | None = None     # [{citation, substance, relevant: bool}] — пер-источник отметки
    role: str | None = None
    note: str | None = None

@app.post("/review")
def review_answer(r: AnswerReview):
    """Записать оценку ВЫДАЧИ (правильно ли система достала первичку и собрала ответ). Подписывается."""
    try:
        rec = answer_review.add(r.question, r.verdict, by=r.by, answer=r.answer, top_score=r.top_score,
                                data_ok=r.data_ok, useful=r.useful, sources=r.sources, note=r.note, role=r.role)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    hygiene.audit("review", r.question, {"verdict": r.verdict, "by": r.by, "useful": r.useful})
    return {"saved": True, "review": rec}

@app.get("/reviews")
def reviews(limit: int = 100):
    """Дашборд качества выдачи: сводка оценок + последние записи (кто/когда/вердикт)."""
    return {**answer_review.summary(), "records": answer_review.records(limit=limit),
            "meta": answer_review._load().get("_meta")}

@app.get("/erg/{name}")
def erg_info(name: str):
    """Расстояния изоляции/эвакуации ERG-2024 + ООН/ДОПОГ. Ориентир первого реагирования, не норматив РФ."""
    s, _ = _resolve_sub(name)
    ckey = s["name"].lower() if s else name.lower()
    e = ERG.get(ckey)
    if not e:
        return {"error": "нет данных ERG для вещества", "known": sorted(ERG.keys())}
    return {"substance": (s or {}).get("name") or name, **e, "disclaimer": ERG_META.get("disclaimer")}

@app.get("/sanpin/{name}")
def sanpin_info(name: str):
    """Справка СанПиН 1.2.3685-21: ПДК, класс, расшифровка особых отметок (О/К/А/Ф/кожа)."""
    s, _ = _resolve_sub(name)
    if not s: return {"error": "вещество не найдено"}
    sp = sanpin.summary(s)
    return {"substance": s["name"], **(sp or {"flags": [], "pdk_mgm3": s.get("pdk_mgm3"),
            "hazard_class": s.get("hazard_class"), "note": "особых отметок нет"})}

@app.get("/guidance/{name}")
def guidance(name: str):
    """Типовое руководство по химической группе (СИЗ/первая помощь/хранение). НЕ паспорт вещества."""
    s, _ = _resolve_sub(name)
    if not s: return {"error": "вещество не найдено"}
    return {"substance": s["name"], **baseline.baseline_for(s)}

@app.get("/emergency/{name}")
def emergency(name: str):
    """Аварийная карточка: ООН-номер + класс ДОПОГ (АХОВ) + первая помощь/СИЗ из паспорта."""
    key = name.lower()
    card = AHOV.get("cards", {}).get(key)
    s, _ = _resolve_sub(name)           # распознаём и по синониму
    ckey = s["name"].lower() if s else key
    if s and not card:                  # карточка АХОВ — по каноническому имени
        card = AHOV.get("cards", {}).get(ckey)
    erg = ERG.get(ckey)                  # ERG/ДОПОГ-карточка (ООН + расстояния эвакуации)
    s = s or {}
    if not card and not s and not erg:
        return {"error": "вещество не найдено", "ahov_known": sorted(AHOV.get("cards", {}).keys())}
    tr = transport.for_cas(s.get("cas")) if s else None   # ООН/ERG из PubChem (для не-АХОВ — дополняет базу)
    g = baseline.baseline_for(s) if s else None
    idlh = _idlh_for(s)
    # АХОВ, если есть карточка АХОВ ИЛИ ERG-данные (токсичный газ с зоной заражения).
    is_ahov = bool((card and card.get("ahov")) or erg)
    # ООН-номер: приоритет кураторских АХОВ/ERG; иначе — из PubChem (первая форма), помечен needs_review.
    un_fallback = tr["un"][0]["un"] if (tr and tr.get("un")) else None
    return {"substance": s.get("name") or name, "is_ahov": is_ahov,
            "un_number": (card or {}).get("un") or (erg or {}).get("un_number") or un_fallback,
            "adr_class": (card or {}).get("adr_class") or (erg or {}).get("adr_class"),
            "erg": erg,                  # расстояния изоляции/эвакуации (ERG-2024), needs_review
            "transport": tr,             # полная транспортная идентификация (ООН/формы/метки) из PubChem
            "emergency_note": (card or {}).get("note"),
            "hazard_class": s.get("hazard_class"), "pdk_mgm3": s.get("pdk_mgm3"),
            # Острый порог IDLH (NIOSH) — когда без СИЗ опасно для жизни; needs_review.
            "idlh": idlh,
            # Особые отметки СанПиН (О/К/А/Ф/кожа) — меняют режим контроля и СИЗ.
            "sanpin_flags": sanpin.decode(s.get("special"), s.get("skin_hazard")) if s else [],
            # Паспортные поля; если пусто — типовое по группе с явной пометкой источника.
            "first_aid": s.get("first_aid") or (g["first_aid"]["value"] if g else None),
            "ppe": s.get("ppe") or (g["ppe"]["value"] if g else None),
            "data_grade": g["grade"] if g else None,
            "guidance_source": ("паспорт" if s.get("first_aid") else "типовое по группе") if s else None,
            "disclaimer": AHOV.get("_meta", {}).get("disclaimer"),
            "confidence": "needs_review" if (card or erg) else "нет АХОВ-карточки"}

@app.get("/substances/names")
def substance_names(prefix: str = "", limit: int = 30):
    """Имена веществ для автодополнения UI (по имени и русским синонимам Wikidata)."""
    p = prefix.lower().strip()
    names = [n for n in SUBS if (not p or p in n)]
    names.sort(key=lambda n: (not n.startswith(p), n))
    out = list(names[:limit])
    # добор по синонимам: если запрос совпал с синонимом — подсказываем каноническое имя
    if p and len(out) < limit:
        hit = sorted({canon for syn, canon in SYN_INDEX.items()
                      if p in syn and canon in SUBS and canon not in out})
        out.extend(hit[:limit - len(out)])
    return {"names": out[:limit], "total": len(SUBS)}

@app.get("/compat")
def compat_check(a: str = Query(...), b: str = Query(...)):
    """Совместимость хранения пары веществ (сегрегация несовместимых)."""
    sa, _ = _resolve_sub(a)
    sb, _ = _resolve_sub(b)
    if not sa or not sb:
        miss = a if not sa else b
        return {"error": f"вещество не найдено: {miss}"}
    r = compat.check(sa, sb)
    hygiene.audit("compat", f"{a} + {b}", {"verdict": r["verdict"]})
    return r

def _pubchem_for(s):
    """Эталонная GHS-запись PubChem по CAS (или None)."""
    cas = (s or {}).get("cas")
    rec = PUBCHEM.get(cas) if cas else None
    return rec if rec else None

@app.get("/ghs/{name}")
def ghs(name: str):
    """GHS-профиль: пиктограммы СГС + сигнальное слово (паспорт) + сверка с эталоном PubChem."""
    s, _ = _resolve_sub(name)
    if not s:
        return {"error": "вещество не найдено"}
    prof = ghs_map.ghs_profile(s)
    out = {"substance": s["name"], **prof}
    pc = _pubchem_for(s)
    if pc:
        our = [p["code"] for p in prof.get("pictograms", [])]
        out["pubchem"] = {"pictograms": pc.get("pictograms"), "signal_word": pc.get("signal_word"),
                          "h_codes": pubchem.decode_hcodes(pc.get("h_codes")),
                          "crosscheck": pubchem.crosscheck(our, pc.get("pictograms")),
                          "source": pc.get("source")}
    return out

@app.get("/pubchem/{name}")
def pubchem_ghs(name: str):
    """Эталонная GHS-классификация PubChem (H-коды по ГОСТ 31340) + сверка с нашими знаками."""
    s, _ = _resolve_sub(name)
    if not s:
        return {"error": "вещество не найдено"}
    pc = _pubchem_for(s)
    if not pc:
        return {"substance": s["name"], "pubchem": None, "note": "нет данных PubChem для CAS"}
    our = [p["code"] for p in ghs_map.ghs_profile(s).get("pictograms", [])]
    return {"substance": s["name"], "cid": pc.get("cid"),
            "pictograms": pc.get("pictograms"), "signal_word": pc.get("signal_word"),
            "h_codes": pubchem.decode_hcodes(pc.get("h_codes")),
            "crosscheck": pubchem.crosscheck(our, pc.get("pictograms")),
            "source": pc.get("source"), "needs_review": True}

class Zone(BaseModel):
    substance: str
    q0_t: float
    wind_ms: float = 1.0
    temp_c: float = 20.0
    stability: str = "изотермия"
    n_hours: float = 1.0
    spill: str = "свободный"
    dike_h: float | None = None

@app.post("/zone")
def zone(z: Zone):
    """Прогноз глубины зоны заражения АХОВ по РД 52.04.253-90 (needs_review)."""
    if rd_zone is None:
        return {"error": "rd_ahov.json не загружен — расчёт зоны недоступен"}
    r = rd_zone.calc(z.substance, z.q0_t, wind=z.wind_ms, temp=z.temp_c,
                     stability=z.stability, n_hours=z.n_hours, spill=z.spill, dike_h=z.dike_h)
    if "error" not in r:
        hygiene.audit("zone", z.substance, {"q0_t": z.q0_t, "depth_km": r.get("depth_total_km")})
    return r

@app.get("/zone/substances")
def zone_substances():
    """Список АХОВ, для которых есть верифицированные коэффициенты РД 52.04.253-90."""
    if rd_zone is None:
        return {"available": []}
    return {"available": sorted(rd_zone.AHOV.keys()),
            "not_in_rd": rd_zone._RD["_meta"].get("not_in_rd", [])}

@app.get("/passport/{name}")
def passport(name: str):
    """Состояние паспорта: полнота критичных полей + статус верификации."""
    s, _ = _resolve_sub(name)
    if not s:
        return {"error": "вещество не найдено"}
    return hygiene.passport_state(s)

@app.get("/quality")
def quality():
    """Дэшборд качества базы: верификация, тиры, дыры в критичных полях."""
    return hygiene.quality_dashboard(R.subs)

@app.get("/audit")
def audit(n: int = 50):
    """Последние записи аудит-лога запросов (комплаенс)."""
    return {"recent": hygiene.audit_tail(n)}

# ---------------------------------------------------------------------------------------------------
# Реестр площадок в публичную поставку НЕ входит: репозиторий не содержит сведений о юридических
# лицах (см. DATA-LICENSE.md, раздел 4). Пользователь подключает собственный реестр через
# PLANTS_FILE. Пока он не подключён, функции по площадке обязаны объяснять положение дел, а не
# изображать «завод не найден» — иначе человек будет искать опечатку в названии.
# ---------------------------------------------------------------------------------------------------
REGISTRY_ABSENT = {
    "error": "реестр площадок не подключён",
    "detail": ("В поставку HEFEST реестр предприятий не входит — публичный репозиторий не содержит "
               "сведений о юридических лицах. Подключите собственный реестр: положите файл в data/ "
               "и укажите его в переменной окружения PLANTS_FILE. Схема и пример — "
               "data/plants.example.json, порядок — DATA-LICENSE.md, раздел 4."),
    "plants": [],
}


def _registry_connected() -> bool:
    return bool(R.plants)


def _plant_missing(name=None):
    """Ответ на запрос по площадке: либо реестра нет вовсе, либо в нём нет такой площадки."""
    if not _registry_connected():
        return dict(REGISTRY_ABSENT)
    return {"error": "площадка не найдена в подключённом реестре",
            "requested": name,
            "known": [x["plant"] for x in R.plants.values()]}


def _resolve_plant(name: str):
    key = name.lower().strip()
    if key in R.plants:
        return R.plants[key]
    for trig, k in R.plant_triggers.items():
        if trig in key or key in trig:
            return R.plants.get(k)
    for pk, p in R.plants.items():
        if key in pk:
            return p
    return None

@app.get("/registry")
def registry_list():
    """Список площадок с числом веществ и опасных пар (авто-аудит совместимости).

    Без подключённого реестра возвращает пустой список с объяснением — см. REGISTRY_ABSENT."""
    if not _registry_connected():
        return dict(REGISTRY_ABSENT)
    out = []
    for p in R.plants.values():
        s = registry.summary(p, SUBS)
        out.append({"plant": s["plant"], "inn": s["inn"], "substances": s["substances_total"],
                    "forbidden_pairs": s["forbidden_pairs"], "caution_pairs": s["caution_pairs"]})
    out.sort(key=lambda x: (-x["forbidden_pairs"], -x["caution_pairs"]))
    return {"plants": out}

@app.get("/registry/{name}")
def registry_plant(name: str):
    """Реестр веществ площадки + опасные пары для совместного хранения."""
    p = _resolve_plant(name)
    if not p:
        return _plant_missing(name)
    return registry.summary(p, SUBS)

@app.get("/export/registry.csv")
def export_registry(plant: str = Query(...)):
    """Экспорт реестра площадки в CSV (для 1С / Excel)."""
    p = _resolve_plant(plant)
    if not p:
        # Причина отказа важна и здесь: без реестра выгружать нечего в принципе.
        сообщение = ("реестр площадок не подключён — см. DATA-LICENSE.md, раздел 4"
                     if not _registry_connected() else "площадка не найдена в подключённом реестре")
        return Response(сообщение, status_code=404, media_type="text/plain; charset=utf-8")
    rows = registry.registry(p, SUBS)
    buf = io.StringIO(); buf.write("﻿")  # BOM для Excel-кириллицы
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Вещество", "Формула", "CAS", "Класс опасности", "ПДК мг/м3", "Группы", "Полнота данных",
                "Количество", "Место хранения", "Ответственный"])
    for r in rows:
        w.writerow([r["name"], r["formula"], r["cas"], r["hazard_class"], r["pdk_mgm3"],
                    " / ".join(r["groups"]), r["data_grade"], "", "", ""])
    from urllib.parse import quote as _q
    ascii_fn = "registry_" + (p.get("inn") or "plant") + ".csv"      # ASCII-safe для старых клиентов
    utf_fn = _q("реестр_" + (p["plant"][:30]) + ".csv")              # RFC 5987 — кириллица в Excel/браузере
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=\"{ascii_fn}\"; filename*=UTF-8''{utf_fn}"})

@app.get("/quiz/{name}")
def quiz_endpoint(name: str):
    """Обучающий квиз по веществу (детерминирован из паспорта, не генерируется ИИ)."""
    s, _ = _resolve_sub(name)
    if not s:
        return {"error": "вещество не найдено"}
    return quiz.build_quiz(s)

# --- Расширение: инструменты для площадок (СИЗ / склад / инспектор / отходы / диспетчер) -----------
@app.get("/ppe/{name}")
def ppe_recommend(name: str, operation: str | None = None):
    """Подбор СИЗ по веществу: паспортные (grade=passport) или типовые по группе (grade=baseline)."""
    s, _ = _resolve_sub(name)
    if not s:
        return {"error": "вещество не найдено"}
    r = ppe.recommend_ppe(s, operation)
    hygiene.audit("ppe", name, {"grade": r["ppe"]["grade"]})
    return r

@app.get("/warehouse/{name}")
def warehouse_map(name: str):
    """Карта склада: зональный аудит совместимости (раскладка — demo-шаблон, вердикты из compat)."""
    p = _resolve_plant(name)
    if not p:
        return _plant_missing(name)
    return warehouse.audit(p, SUBS)

@app.get("/inspection/{plant}")
def inspection_readiness(plant: str):
    """Режим инспектора: химическая готовность площадки ПО ДАННЫМ системы (не проверочный лист надзора)."""
    p = _resolve_plant(plant)
    if not p:
        return _plant_missing(plant)
    return inspection.plant_readiness(p, SUBS, assemble=_assemble)

class WasteComponentIn(BaseModel):
    substance: str
    Ci_fraction: float | None = None  # массовая доля 0..1

class WasteEstimateIn(BaseModel):
    components: list[WasteComponentIn]

@app.post("/waste/estimate")
def waste_estimate(req: WasteEstimateIn):
    """Предварительный расчёт класса опасности ОТХОДА (I–V) по Приказу Минприроды № 536.
    Класс не присваиваем при нехватке показателей — honest-gap, needs_review (см. waste_calc)."""
    comps = [{"substance": c.substance, "Ci_fraction": c.Ci_fraction} for c in req.components]
    return waste_calc.estimate_waste_class(comps)

@app.get("/dispatch/{name}")
def dispatch_card_endpoint(name: str, mass_kg: float | None = None, wind_ms: float = 1.0,
                           temp_c: float = 20.0, stability: str = "изотермия",
                           n_hours: float = 1.0, spill: str = "свободный",
                           dike_h: float | None = None):
    """Оперативная карточка диспетчера при аварии с АХОВ: зона (РД 52.04.253-90) +
    первоочередные действия из /emergency + поведение по плотности + чек-лист оповещения.
    Зоны — строго из методики; телефоны — плейсхолдеры предприятия; ничего не выдумываем."""
    em = emergency(name)
    if isinstance(em, dict) and em.get("error") and not em.get("substance"):
        return em
    weather = {"wind_ms": wind_ms, "temp_c": temp_c, "stability": stability,
               "n_hours": n_hours, "spill": spill, "dike_h": dike_h}
    r = dispatch.dispatch_card(name, mass_kg=mass_kg, weather=weather, emergency=em)
    hygiene.audit("dispatch", name, {"mass_kg": mass_kg, "depth_km": r.get("zone", {}).get("depth_total_km")})
    return r

@app.get("/shift/{name}")
def shift_alert_endpoint(name: str, value: float | None = None, unit: str | None = None):
    """Реакция на превышение (мастер смены): измеренная концентрация vs ПДК/IDLH, СИЗ, АХОВ-флаг.
    Единицы НЕ пересчитываем — кратность только при совпадении единиц, иначе honest-gap (см. shift_alert)."""
    s, _ = _resolve_sub(name)
    if not s:
        return {"error": "вещество не найдено"}
    em = emergency(name)
    em = em if isinstance(em, dict) else None
    r = shift_alert.assess_exceedance(s, value=value, unit=unit, emergency=em)
    hygiene.audit("shift", name, {"value": value, "unit": unit, "severity": r.get("severity")})
    return r

@app.get("/qr/{name}")
def qr(name: str, request: Request, target: str | None = None):
    """QR-код (SVG), ведущий на карточку вещества — для стикера на ёмкости/рабочем месте."""
    if segno is None:
        return Response("segno not installed", status_code=503)
    base = str(request.base_url).rstrip("/")
    url = target or f"{base}/card/{name}"
    out = io.BytesIO()
    segno.make(url, error="m").save(out, kind="svg", scale=4, dark="#0a0e14", light="#ffffff", border=2)
    return Response(out.getvalue(), media_type="image/svg+xml")

@app.get("/card/{name}", response_class=HTMLResponse)
def card(name: str):
    """Мобильная карточка вещества (цель QR-кода): класс, ПДК, первая помощь, СИЗ, АХОВ."""
    s, _ = _resolve_sub(name)
    if not s:
        return HTMLResponse(f"<h2>Вещество не найдено: {_html.escape(name)}</h2>", status_code=404)
    g = baseline.baseline_for(s)
    gh = ghs_map.ghs_profile(s)
    ac = AHOV.get("cards", {}).get(s["name"].lower())
    idlh = _idlh_for(s)
    e = _html.escape
    def field(lbl, val, src=None):
        tag = f' <span class="bt">типовое</span>' if src == "типовое по группе" else ""
        return f'<div class="f"><div class="k">{lbl}</div><div class="v">{e(str(val) or "—")}{tag}</div></div>'
    ahov_html = (f'<div class="ahov">⚠ АХОВ · ООН {e(ac.get("un",""))} · класс ДОПОГ {e(ac.get("adr_class",""))}</div>'
                 if ac and ac.get("ahov") else "")
    idlh_html = (f'<div class="idlh"><b>IDLH {e(idlh["idlh"])} {e(idlh.get("units") or "")}</b> — '
                 f'острый порог: выше этого без изолирующего СИЗ опасно для жизни (NIOSH)</div>'
                 if idlh else "")
    sig = gh.get("signal_word") or ""
    from urllib.parse import quote as _q
    _enc = _q(s["name"])
    _is_ahov = bool((ac and ac.get("ahov")) or ERG.get(s["name"].lower()))  # как в /emergency (учитывает ERG)
    acts_html = ('<div class="acts">'
                 f'<a href="/ppe.html?name={_enc}">Подбор СИЗ</a>'
                 + (f'<a class="em" href="/dispatch.html?name={_enc}">Карточка диспетчера</a>'
                    if _is_ahov else "")
                 + "</div>")
    html_doc = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(s['name'])}</title>
<style>body{{margin:0;background:#0a0e14;color:#e6edf3;font:16px/1.55 system-ui,-apple-system,sans-serif;padding:16px}}
.c{{max-width:520px;margin:0 auto}}h1{{font-size:22px;margin:0 0 4px}}.sub{{color:#8b97a7;font-size:13px;margin-bottom:14px}}
.ahov{{background:#2a1414;border:1px solid #5a2626;color:#ff9b9b;border-radius:10px;padding:10px 13px;font-weight:600;margin-bottom:12px}}
.sig{{display:inline-block;font-weight:700;padding:5px 12px;border-radius:8px;margin-bottom:12px;background:#3a1518;color:#ff8d8d;border:1px solid #5a2025}}
.idlh{{background:#241a08;border:1px solid #5a4216;color:#fcd9a0;border-radius:10px;padding:9px 12px;font-size:13px;margin-bottom:12px}}
.f{{border-top:1px solid #28344a;padding:11px 0}}.k{{font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:#8b97a7;margin-bottom:3px}}
.v{{font-size:15px}}.bt{{font-family:monospace;font-size:10px;color:#fbd56b;border:1px solid #5a4920;background:#3a2e12;padding:1px 6px;border-radius:5px}}
.d{{margin-top:14px;font-size:12px;color:#8b97a7}}
.acts{{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}}
.acts a{{flex:1;min-width:140px;text-align:center;text-decoration:none;padding:12px;border-radius:9px;font-size:14px;font-weight:600;background:#11202e;border:1px solid #284a5e;color:#7fd1ff}}
.acts a.em{{background:#241208;border-color:#5a3a16;color:#ffb37a}}</style></head><body><div class="c">
<h1>{e(s['name'])}</h1><div class="sub">{e(s.get('formula') or '')} · CAS {e(s.get('cas') or '—')}</div>
{ahov_html}{f'<div class="sig">⚠ {e(sig)}</div>' if sig else ''}{idlh_html}
{field("Класс опасности", s.get('hazard_class'))}
{field("ПДК рабочей зоны", (str(s.get('pdk_mgm3'))+' мг/м³') if s.get('pdk_mgm3') else '—')}
{field("Первая помощь", g['first_aid']['value'], g['first_aid']['source'])}
{field("Средства защиты (СИЗ)", g['ppe']['value'], g['ppe']['source'])}
{field("Хранение", g['storage']['value'], g['storage']['source'])}
{acts_html}
<div class="d">Данные с пометкой «типовое» — общие по группе, сверьте с паспортом. Цена ошибки = здоровье.</div>
</div></body></html>"""
    return HTMLResponse(html_doc)

@app.get("/metrics")
def metrics():
    return {"corpus": {"substances": len(R.subs), "chunks": len(R.chunks)},
            "cache": CACHE.stats, "cache_hit_rate": round(CACHE.hit_rate(), 3)}
