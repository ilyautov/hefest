# -*- coding: utf-8 -*-
"""
Гибридный retriever по корпусу SDS.
Сигналы: char-wb TF-IDF + word TF-IDF + BM25 + сущностный буст (вещество) +
интент раздела + опциональный scope по заводу.
Эмбеддинги абстрагированы: лексический бэкенд по умолчанию (офлайн, песочница),
семантический (Ollama bge-m3 / multilingual-e5) подключается через backends.py в проде.
"""
import json, os, re, math, urllib.request
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from rank_bm25 import BM25Okapi

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")

RU_STOP = set("и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне было вот от меня еще нет о из ему когда даже ну вдруг ли если уже или ни быть был него до вас нибудь опять уж вам ведь там потом себя ничего ей может они тут где есть надо ней для мы тебя их чем была сам чтоб без будто чего раз тоже себе под будет ж тогда кто этот того потому этого какой совсем ним здесь этом один почти мой тем чтобы нее были куда зачем всех никогда можно при наконец два об другой хоть после над больше тот через эти нас про всего них какая много разве три эту нужны нужен нужно какие какой чем при это как".split())

def toks(t):
    return [w for w in re.findall(r"[а-яёa-z0-9]+", t.lower()) if len(w) > 2 and w not in RU_STOP]

# Интенты разделов: ключевые слова запроса -> название раздела
SECTION_INTENT = {
    "Раздел 4. Меры первой помощи": ["помощь","ожог","попал","глаз","проглот","вдыхан","антидот","отравлен","промыть"],
    "Раздел 5. Меры пожаротушения": ["пожар","вспыш","тушить","горит","воспламен","огнетушит","взрыв"],
    "Раздел 6. Меры при аварийном выбросе": ["разлив","утечк","выброс","авари","собрать","нейтрализ"],
    "Раздел 7. Обращение и хранение": ["хранить","хранен","хранить","совместим","несовместим","рядом","склад","тара"],
    "Раздел 8. Средства защиты (СИЗ) и контроль": ["сиз","перчатк","респиратор","очки","защит","противогаз","костюм"],
    "Раздел 11. Токсикологическая информация": ["пдк","токсич","концентрац","рабочей зоны","канцероген"],
    "Раздел 2. Идентификация опасности": ["опасн","класс опасн","чем опасен","риск"],
}

class HybridRetriever:
    def __init__(self, lexical=True):
        c = json.load(open(os.path.join(DATA, os.getenv("CORPUS_FILE", "corpus_full_clean.json")),encoding="utf-8"))
        self.chunks = c["chunks"]
        self.subs = json.load(open(os.path.join(DATA, os.getenv("SUBS_FILE", "substances_clean.json")),encoding="utf-8"))
        # Реестр предприятий НЕОБЯЗАТЕЛЕН и в поставку не входит: публичный репозиторий не
        # содержит сведений о юридических лицах (см. DATA-LICENSE.md, раздел 4). Пользователь
        # подключает собственный реестр через PLANTS_FILE; без него функции по площадке честно
        # сообщают, что реестр не подключён, а всё остальное работает как обычно.
        self.plants = self._load_plants()
        texts = [f'{x["text"]} {x["substance"]} {x["section"]}' for x in self.chunks]
        # лексические сигналы (char+word TF-IDF + BM25) — тяжёлые на 26010 чанков.
        # семантическому ретриверу не нужны: lexical=False пропускает их построение.
        if lexical:
            self.word = TfidfVectorizer(tokenizer=toks, token_pattern=None, ngram_range=(1,2), min_df=1)
            self.char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3,5), min_df=1, lowercase=True)
            self.Wm = self.word.fit_transform(texts)
            self.Cm = self.char.fit_transform(texts)
            self.bm25 = BM25Okapi([toks(t) for t in texts])
        # сущностные триггеры: substance -> (stems, synonyms, exact)
        GENERIC = {"кислота","кислоты","натрия","калия","газ","железа","водорода","углерода",
                   "аммония","бора","натрий","триоксид","ангидрид","синильная"}
        SYN_ENTITY = {
            "гидроксид натрия": ["едкий натр","едкого натра","каустик","каустическая сода","натр едкий","щелоч","щёлоч"],
            "окись этилена": ["этиленоксид","оксид этилена","этилен оксид","этиленокс"],
            "аммиак": ["нашатыр"],
            "циановодород (синильная кислота)": ["синильн","цианистоводород"],
            "оксид углерода": ["угарн"],
            "гипохлорит натрия": ["белизна","жидкий хлор","активный хлор"],
            "серная кислота": ["купорос"],
        }
        self.entity = {}
        for s in self.subs:
            nm = s["name"].lower()
            stems = set()
            for w in re.findall(r"[а-яёa-z0-9]+", nm):
                if len(w) > 4 and w not in GENERIC:
                    stems.add(w[:5])
            exact = set()
            if s.get("formula"): exact.add(s["formula"].lower())
            if s.get("cas"): exact.add(s["cas"])
            self.entity[s["name"]] = (stems, set(SYN_ENTITY.get(nm, [])), exact)
        self.doc_sub = [x["substance"] for x in self.chunks]
        self.plant_triggers = self._build_plant_triggers()


    # ------------------------------------------------------------------------------------
    # Реестр площадок. Отсутствие файла — штатное состояние поставки, а не ошибка.
    # ------------------------------------------------------------------------------------
    @staticmethod
    def _load_plants():
        path = os.path.join(DATA, os.getenv("PLANTS_FILE", "plants_linked.json"))
        try:
            with open(path, encoding="utf-8") as fh:
                registry = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            return {}
        return {p["plant"].lower(): p for p in registry.get("plants", []) if p.get("plant")}


    # ------------------------------------------------------------------------------------
    # Распознавание площадки в запросе. Названия предприятий НЕ хардкодятся в коде: они
    # приходят из реестра (PLANTS_FILE) плюс необязательный словарь разговорных псевдонимов
    # data/plant_aliases.json. Благодаря этому подмена реестра на обезличенный действительно
    # обезличивает систему целиком, а не только выдачу (см. engine/anonymize_plants.py).
    # ------------------------------------------------------------------------------------
    _СТОП_СЛОВА = {"завод", "гк", "ооо", "оао", "пао", "ао", "зао", "опытный", "химическое",
                   "предприятие", "комбинат", "им", "имени", "групп", "группа"}

    def _build_plant_triggers(self):
        triggers = {}

        # 1. Автотриггеры из самих названий: значимые токены длиной от 4 символов.
        for key, plant in self.plants.items():
            triggers.setdefault(key, key)
            for token in re.split(r"[^\w-]+", key):
                token = token.strip("-")
                if len(token) >= 4 and token not in self._СТОП_СЛОВА:
                    triggers.setdefault(token, key)

        # 2. Разговорные псевдонимы из данных — только если цель есть в загруженном реестре.
        try:
            path = os.path.join(DATA, os.getenv("PLANT_ALIASES_FILE", "plant_aliases.json"))
            with open(path, encoding="utf-8") as fh:
                aliases = json.load(fh).get("aliases", {})
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            aliases = {}
        for alias, key in aliases.items():
            if key in self.plants:
                triggers[alias.lower()] = key

        # Порядок критичен: совпадение ищется перебором подстрок, первое выигрывает. Более
        # длинный (специфичный) триггер обязан проверяться раньше короткого — иначе составное
        # название площадки перехватывается общим токеном, который есть и у соседней площадки.
        return dict(sorted(triggers.items(), key=lambda пара: (-len(пара[0]), пара[0])))

    def _entity_hits(self, ql):
        hits = set()
        for name, (stems, syns, exact) in self.entity.items():
            if any(st in ql for st in stems) or any(sy in ql for sy in syns) or any(e in ql for e in exact if len(e) > 3):
                hits.add(name)
        return hits

    def _plant_scope(self, ql):
        for trig, key in self.plant_triggers.items():
            if trig in ql and key in self.plants:
                return set(self.plants[key].get("matched_substances", []))
        return None

    def query(self, q, k=3, scope_substances=None):
        ql = q.lower()
        qw = self.word.transform([q]); qc = self.char.transform([q])
        s_word = cosine_similarity(qw, self.Wm)[0]
        s_char = cosine_similarity(qc, self.Cm)[0]
        bm = np.array(self.bm25.get_scores(toks(q)))
        bm = bm / (bm.max() + 1e-9)
        score = 0.30*s_word + 0.40*s_char + 0.30*bm
        # сущностный буст
        ents = self._entity_hits(ql)
        # интент раздела
        intent_secs = [sec for sec, kws in SECTION_INTENT.items() if any(kw in ql for kw in kws)]
        # scope по заводу (явный аргумент или из текста запроса)
        scope = scope_substances or self._plant_scope(ql)
        for i, ch in enumerate(self.chunks):
            if ch["substance"] in ents: score[i] += 0.22
            if intent_secs and ch["section"] in intent_secs: score[i] += 0.12
            if scope is not None:
                if ch["substance"] in scope: score[i] += 0.15
                else: score[i] -= 0.10
        idx = score.argsort()[::-1][:k]
        return [(self.chunks[i], float(score[i])) for i in idx]

class SemanticRetriever(HybridRetriever):
    """Семантический retrieval (Ollama bge-m3) поверх data/embeddings.npy + плант-скоуп.
    Конфиг C из semantic_hybrid_eval: на полной базе (2601) семантика держит top-1 84%,
    плант-скоуп чинит 33%->100% без потери предметного top-1, а сущностный/интент-слои
    лексического гибрида на масштабе шумят -> здесь не применяются. Тот же интерфейс
    .query(q, k, scope_substances), что у HybridRetriever -> сервис свопает класс по env."""
    def __init__(self, emb_path=None, host=None, model=None, scope_in=0.15, scope_out=-0.10,
                 reranker=None, rerank_n=20):
        super().__init__(lexical=False)
        self.host = host or os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
        self.model = model or os.getenv("EMBED_MODEL", "bge-m3")
        self.scope_in, self.scope_out = scope_in, scope_out
        self.reranker = reranker          # опц. кросс-энкодер: retrieve top-N косинусом -> реранк -> top-k
        self.rerank_n = rerank_n
        M = np.load(emb_path or os.path.join(DATA, os.getenv("EMB_FILE", "embeddings_clean.npy"))).astype(np.float32)
        self.chunks = self.chunks[:len(M)]                       # выравниваем на длину индекса
        self.subs_arr = np.array([c["substance"] for c in self.chunks])
        self.Mn = M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)

    def _embed(self, text):
        req = urllib.request.Request(f"{self.host}/api/embed",
            data=json.dumps({"model": self.model, "input": [text]}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())["embeddings"][0]

    def query(self, q, k=3, scope_substances=None):
        ql = q.lower()
        qv = np.asarray(self._embed(q), dtype=np.float32); qv /= (np.linalg.norm(qv) + 1e-9)
        score = self.Mn @ qv                                     # семантическая база (косинус)
        scope = scope_substances or self._plant_scope(ql)        # плант-скоуп срабатывает только на плант-запросах
        if scope is not None:
            insc = np.isin(self.subs_arr, list(scope))
            score = score + np.where(insc, self.scope_in, self.scope_out)
        if self.reranker is None:
            idx = score.argsort()[::-1][:k]
            return [(self.chunks[i], float(score[i])) for i in idx]
        # кросс-энкодер реранк: пул top-N по косинусу(+скоуп) -> реранк -> top-k
        pool = score.argsort()[::-1][:self.rerank_n]
        cands = [self.chunks[i] for i in pool]
        return self.reranker.rerank(q, cands, top_k=k)


if __name__ == "__main__":
    r = HybridRetriever()
    # Демо-запросы. Название площадки берётся из загруженного реестра, а не зашивается в код,
    # чтобы самотест работал и на обезличенном, и на собственном реестре предприятия.
    площадка = next(iter(r.plants), None)
    примеры = ["как хранить серную кислоту", "антидот при отравлении цианидом"]
    if площадка:
        примеры.append(f"что опасного на площадке {площадка}")
    for q in примеры:
        top = r.query(q, k=1)[0]
        print(f"{q[:40]:40} -> {top[0]['substance']} / {top[0]['section'][:28]} ({top[1]:.2f})")
