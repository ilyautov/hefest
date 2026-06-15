# -*- coding: utf-8 -*-
"""
Русские синонимы веществ из Wikidata (лицензия CC0, можно on-prem). Чинит recall поиска:
пользователь пишет «оксиран / окись этилена / этиленоксид» — все они должны вести к одному
веществу. Тянем rdfs:label@ru и skos:altLabel@ru по CAS-номеру (P231).

Через ОСНОВНОЙ API Wikidata (action=query haswbstatement → QID, затем wbgetentities батчами),
а не WDQS/SPARQL (тот периодически режет до 1 req/min). QID кэшируются — повторный/прерванный
запуск дешёвый и возобновляемый.

ПРИНЦИП БЕЗОПАСНОСТИ: синонимы НЕ генерируются — только из Wikidata (CC0), с источником.
Это идентификаторы (имена), не регуляторные значения.

Запуск:  python3 engine/fetch_synonyms.py [limit]
Результат: data/synonyms.json {canonical_name_lower: {cas, qid, synonyms:[...], source}}
"""
import sys, os, re, json, time, urllib.request, urllib.parse

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
OUT = os.path.join(DATA, "synonyms.json")
QCACHE = os.path.join(DATA, "_wd_qid_cache.json")
API = "https://www.wikidata.org/w/api.php"
UA = {"User-Agent": "rag-sds-pilot/1.0 (chemical-safety; on-prem RAG)"}


def _api(params):
    params["format"] = "json"
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers=UA)
            return json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
        except urllib.error.HTTPError as ex:
            if ex.code == 429 and attempt < 5:
                time.sleep(5 * (attempt + 1)); continue
            raise


def _qid_by_cas(cas):
    d = _api({"action": "query", "list": "search",
              "srsearch": f"haswbstatement:P231={cas}", "srlimit": 1})
    r = d.get("query", {}).get("search", [])
    return r[0]["title"] if r else None


def _entities_ru(qids):
    out = {}
    for i in range(0, len(qids), 50):
        d = _api({"action": "wbgetentities", "ids": "|".join(qids[i:i + 50]),
                  "languages": "ru", "props": "labels|aliases"})
        for qid, e in d.get("entities", {}).items():
            lab = e.get("labels", {}).get("ru", {}).get("value")
            al = [a["value"] for a in e.get("aliases", {}).get("ru", [])]
            out[qid] = {"ru_label": lab, "aliases": al}
        time.sleep(0.6)
    return out


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    subs = json.load(open(os.path.join(DATA, "substances_clean.json"), encoding="utf-8"))
    cas_to_name = {}
    for s in subs:
        c = (s.get("cas") or "").strip()
        if c and c not in cas_to_name:
            cas_to_name[c] = s["name"]
    cas_all = list(cas_to_name)
    if limit:
        cas_all = cas_all[:limit]

    qcache = json.load(open(QCACHE, encoding="utf-8")) if os.path.exists(QCACHE) else {}
    print(f"веществ с CAS: {len(cas_all)} | QID в кэше: {len(qcache)}")

    # шаг 1: CAS -> QID (с кэшем)
    for i, cas in enumerate(cas_all, 1):
        if cas in qcache:
            continue
        try:
            qcache[cas] = _qid_by_cas(cas)
        except Exception:
            qcache[cas] = None
        if i % 50 == 0:
            json.dump(qcache, open(QCACHE, "w"), ensure_ascii=False)
            print(f"  QID: {i}/{len(cas_all)}")
        time.sleep(0.32)
    json.dump(qcache, open(QCACHE, "w"), ensure_ascii=False)

    # шаг 2: QID -> рус. метки/синонимы
    qids = sorted({q for c in cas_all if (q := qcache.get(c))})
    print(f"уникальных QID: {len(qids)} — тянем рус. метки…")
    ent = _entities_ru(qids)

    out, total = {}, 0
    for cas in cas_all:
        name = cas_to_name[cas]; qid = qcache.get(cas)
        wd = ent.get(qid) if qid else None
        if not wd:
            continue
        cand = ([wd["ru_label"]] if wd.get("ru_label") else []) + wd.get("aliases", [])
        seen, syns, nlow = set(), [], name.lower().strip()
        for c in cand:
            cl = re.sub(r"\s+", " ", c).strip(); k = cl.lower()
            if not cl or k == nlow or k in seen:
                continue
            seen.add(k); syns.append(cl)
        if syns:
            out[nlow] = {"cas": cas, "qid": qid, "synonyms": syns, "source": "Wikidata (CC0)"}
            total += len(syns)

    meta = {"_meta": {"source": "Wikidata rdfs:label@ru + skos:altLabel@ru по CAS (P231), лицензия CC0",
                      "substances_with_synonyms": len(out), "total_synonyms": total,
                      "note": "Синонимы для распознавания запросов. Не регуляторные данные."}}
    json.dump({**meta, **out}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n✓ {len(out)} веществ получили синонимы ({total} всего) → {OUT}")


if __name__ == "__main__":
    main()
