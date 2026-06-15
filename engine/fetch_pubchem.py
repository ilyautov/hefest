# -*- coding: utf-8 -*-
"""
Авторитетная GHS-классификация из PubChem (NIH, public domain) по CAS: пиктограммы, сигнальное слово,
H-коды (стандартизованные коды опасности СГС). PubChem агрегирует классификации ECHA/NITE/и др.

Зачем: наши знаки СГС выведены из меток паспорта эвристически. PubChem даёт ЭТАЛОННЫЙ набор H-кодов и
пиктограмм с провенансом — для сверки (расхождение = флаг аудитору) и обогащения.

ПРИНЦИП БЕЗОПАСНОСТИ: коды и пиктограммы парсятся из PubChem, не выдумываются. Русский текст H-кодов —
стандартные формулировки ГОСТ 31340-2013/СГС (см. engine/pubchem.py), не перевод «на лету».

Запуск:  python3 engine/fetch_pubchem.py [path_cas_json]
Результат: data/pubchem_ghs.json {cas: {cid, pictograms, signal_word, h_codes, source}}
"""
import sys, os, re, json, time, urllib.request

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
OUT = os.path.join(DATA, "pubchem_ghs.json")
UA = {"User-Agent": "Mozilla/5.0 (rag-sds pilot; chemical-safety research)"}


def _get(url, tries=4):
    for a in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25).read()
        except urllib.error.HTTPError as e:
            if e.code in (503, 429) and a < tries - 1:
                time.sleep(2 * (a + 1)); continue
            return None
        except Exception:
            return None
    return None


def _cid(cas):
    b = _get(f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{cas}/cids/JSON")
    if not b:
        return None
    try:
        return json.loads(b)["IdentifierList"]["CID"][0]
    except Exception:
        return None


def _ghs(cid):
    b = _get(f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON/?heading=GHS+Classification")
    if not b:
        return None
    txt = b.decode("utf-8", "replace")
    pics = sorted(set(re.findall(r"(GHS0[1-9])", txt)))
    sig = "Danger" if '"Danger"' in txt or "Danger" in re.findall(r"Signal[^\"]*\"\s*,\s*\"[^\"]*String\"\s*:\s*\"(\w+)", txt + " ") else ("Warning" if "Warning" in txt else None)
    # сигнальное слово точнее: ищем поле Signal
    m = re.search(r"Signal\".*?\"String\"\s*:\s*\"(Danger|Warning)\"", txt, re.S)
    if m:
        sig = m.group(1)
    hcodes = sorted(set(re.findall(r"\b(H\d{3})\b", txt)))
    if not pics and not hcodes:
        return None
    return {"pictograms": pics, "signal_word": sig, "h_codes": hcodes}


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "/tmp/all_cas.json"
    name_cas = json.load(open(src, encoding="utf-8"))
    out = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    done = set(out)
    items = sorted(set(name_cas.values()))
    found = sum(1 for k in out if k != "_meta")
    for i, cas in enumerate(items, 1):
        if cas in done or cas == "_meta":
            continue
        cid = _cid(cas)
        time.sleep(0.25)
        rec = _ghs(cid) if cid else None
        if rec:
            rec["cid"] = cid; rec["source"] = "PubChem GHS Classification (NIH, public domain)"; rec["needs_review"] = True
            out[cas] = rec; found += 1
            if found % 25 == 0:
                out["_meta"] = {"source": "PubChem GHS (NIH)", "count": found}
                json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
                print(f"[{i}/{len(items)}] найдено {found} (последний {cas}: {rec['pictograms']} {rec['signal_word']})")
        else:
            out[cas] = None  # помечаем «нет в PubChem», чтобы не перезапрашивать
        time.sleep(0.2)
    real = {k: v for k, v in out.items() if v and k != "_meta"}
    out["_meta"] = {"source": "PubChem GHS Classification (NIH, public domain)", "count": len(real),
                    "disclaimer": "Эталонные H-коды/пиктограммы из PubChem (агрегат ECHA/NITE/др.). needs_review. "
                                  "H-коды — по ГОСТ 31340-2013/СГС."}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n✓ {len(real)} веществ с GHS из PubChem → {OUT}")


if __name__ == "__main__":
    main()
