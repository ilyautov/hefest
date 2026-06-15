# -*- coding: utf-8 -*-
"""
Транспортная идентификация опасных грузов из PubChem (NIH, public domain) по CAS:
номер ООН (UN number), номер гида ERG, транспортная метка опасности (DOT Label).

Зачем: номер ООН — международно гармонизированный идентификатор (UN1017 = хлор и в ДОПОГ, и в DOT, и в ООН),
критичен для аварийного реагирования и перевозки. В нашей базе он был у 22 кураторских АХОВ; PubChem
добавляет CAS-привязку для остальных. Гид ERG стыкуется с нашим модулем /emergency (ERG-2024).

ПРИНЦИП БЕЗОПАСНОСТИ: значения парсятся из структурного узла PubChem «Transport Information > DOT ID and Guide»
(а не регэкспом по всему тексту — иначе поймали бы номера из аварийных нарративов). Несколько номеров ООН —
это РАЗНЫЕ ФОРМЫ вещества (безводный / раствор 10-35% / смесь), и форма сохраняется в аннотации. Ничего
не выдумываем; форму выбирает эксперт по реальному продукту. needs_review.

Запуск:  python3 engine/fetch_transport.py [path_name_cas_json]
Результат: data/transport.json {cas: {cid, un:[{un,erg_guide,form}], labels:[...], source, needs_review}}
"""
import sys, os, re, json, time, urllib.request, urllib.error

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
OUT = os.path.join(DATA, "transport.json")
UA = {"User-Agent": "Mozilla/5.0 (rag-sds pilot; chemical-safety research)"}
# «1017 124» / «2672 154(10-35% solution)» -> un, erg, форма
_DOT = re.compile(r"^\s*(\d{4})\s+(\d{2,3})\s*(?:\((.*?)\))?\s*$")


def _get(url, tries=4):
    for a in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()
        except urllib.error.HTTPError as e:
            if e.code in (503, 429) and a < tries - 1:
                time.sleep(2.5 * (a + 1)); continue
            return None
        except Exception:
            if a < tries - 1:
                time.sleep(1.5 * (a + 1)); continue
            return None
    return None


def _cid(cas):
    b = _get(f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{cas}/cids/JSON")
    try:
        return json.loads(b)["IdentifierList"]["CID"][0] if b else None
    except Exception:
        return None


def _node_strings(rec, heading):
    """Все строковые значения узла(ов) с данным TOCHeading."""
    out = []
    def walk(sec):
        if sec.get("TOCHeading") == heading:
            for info in sec.get("Information", []) or []:
                for sm in info.get("Value", {}).get("StringWithMarkup", []) or []:
                    s = (sm.get("String") or "").strip()
                    if s:
                        out.append(s)
        for s in sec.get("Section", []) or []:
            walk(s)
    for s in rec.get("Section", []) or []:
        walk(s)
    return out


def _transport(cid):
    b = _get(f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON/?heading=Safety+and+Hazards")
    if not b:
        return None
    try:
        rec = json.loads(b)["Record"]
    except Exception:
        return None
    uns, seen = [], set()
    for s in _node_strings(rec, "DOT ID and Guide"):
        m = _DOT.match(s)
        if not m:
            continue
        un, erg, form = m.group(1), m.group(2), (m.group(3) or "").strip() or None
        key = (un, form)
        if key not in seen:
            seen.add(key)
            uns.append({"un": un, "erg_guide": erg, "form": form})
    labels = []
    for s in _node_strings(rec, "DOT Label"):
        if s not in labels:
            labels.append(s)
    if not uns and not labels:
        return None
    return {"un": uns, "labels": labels[:4]}


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "/tmp/all_cas.json"
    name_cas = json.load(open(src, encoding="utf-8"))
    out = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    done = set(out)
    items = sorted(set(name_cas.values()))
    found = sum(1 for k, v in out.items() if v and k != "_meta")
    for i, cas in enumerate(items, 1):
        if cas in done or cas == "_meta":
            continue
        cid = _cid(cas)
        time.sleep(0.25)
        rec = _transport(cid) if cid else None
        if rec:
            rec["cid"] = cid
            rec["source"] = "PubChem Transport Information / DOT (NIH, public domain)"
            rec["needs_review"] = True
            out[cas] = rec
            found += 1
            if found % 20 == 0:
                out["_meta"] = {"source": "PubChem Transport (NIH)", "count": found}
                json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
                print(f"[{i}/{len(items)}] найдено {found} (последний {cas}: UN={[u['un'] for u in rec['un']]})", flush=True)
        else:
            out[cas] = None
        time.sleep(0.2)
    real = {k: v for k, v in out.items() if v and k != "_meta"}
    out["_meta"] = {"source": "PubChem Transport Information / DOT (NIH, public domain)", "count": len(real),
                    "disclaimer": "Номер ООН — международный (совпадает с ДОПОГ). Несколько номеров = разные формы "
                                  "вещества (форма в аннотации). Гид ERG — ERG-2024. needs_review."}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n✓ {len(real)} веществ с транспортной идентификацией → {OUT}")


if __name__ == "__main__":
    main()
