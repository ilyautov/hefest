# -*- coding: utf-8 -*-
"""
Физико-химические свойства из PubChem (NIH, public domain) по CAS: температура вспышки, кипения,
плавления, плотность, давление пара, пределы воспламенения (НКПР/ВКПР), растворимость в воде.

Зачем: эти величины безопасно-критичны для решений по ПОЖАРНОЙ безопасности и ХРАНЕНИЮ
(температура вспышки → можно ли рядом с источником огня; НКПР/ВКПР → взрывоопасность смеси;
давление пара → летучесть при разливе). В нашей базе они почти пусты (темп. вспышки 29/2597).

ПРИНЦИП БЕЗОПАСНОСТИ: значения НЕ выдумываются и НЕ нормализуются «на лету». Мы сохраняем СЫРЫЕ строки
из PubChem как есть (часто их несколько из разных справочников, в разных единицах) ВМЕСТЕ с источником.
Никакого выбора «одного правильного» числа алгоритмом — это решает эксперт (needs_review=True).
Если PubChem даёт расходящиеся значения — показываем все, расхождение = сигнал аудитору.

Запуск:  python3 engine/fetch_physchem.py [path_name_cas_json]
Результат: data/physchem.json {cas: {cid, props:{flash_point:[{value,source}], ...}, source, needs_review}}
"""
import sys, os, json, time, urllib.request, urllib.error

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
OUT = os.path.join(DATA, "physchem.json")
UA = {"User-Agent": "Mozilla/5.0 (rag-sds pilot; chemical-safety research)"}

# TOCHeading в PubChem -> наш ключ. Только безопасно-критичные физхим-свойства.
HEADINGS = {
    "Flash Point": "flash_point",
    "Boiling Point": "boiling_point",
    "Melting Point": "melting_point",
    "Density": "density",
    "Vapor Pressure": "vapor_pressure",
    "Flammable Limits": "flammable_limits",   # НКПР/ВКПР (LEL/UEL)
    "LogP": None,                              # игнор (не нужно), оставлено для ясности
    "Solubility": "solubility",
}
_WANT = {k for k, v in HEADINGS.items() if v}


def _get(url, tries=4):
    for a in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()
        except urllib.error.HTTPError as e:
            if e.code in (503, 429) and a < tries - 1:
                time.sleep(2 * (a + 1)); continue
            return None
        except Exception:
            if a < tries - 1:
                time.sleep(1.5 * (a + 1)); continue
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


def _ref_map(record):
    """ReferenceNumber -> человекочитаемый источник (SourceName / SourceID)."""
    out = {}
    for r in record.get("Reference", []) or []:
        num = r.get("ReferenceNumber")
        if num is None:
            continue
        src = r.get("SourceName") or ""
        sid = r.get("Name") or r.get("SourceID") or ""
        out[num] = (src + (f" — {sid}" if sid and sid != src else "")).strip(" —") or src
    return out


def _strings_from_info(info):
    """Достаёт сырые строковые значения из Information.Value (StringWithMarkup или Number)."""
    val = info.get("Value", {}) or {}
    out = []
    for sm in val.get("StringWithMarkup", []) or []:
        s = (sm.get("String") or "").strip()
        if s:
            out.append(s)
    if not out and "Number" in val:
        unit = val.get("Unit", "")
        for n in val["Number"]:
            out.append(f"{n} {unit}".strip())
    return out


def _walk(section, want, refs, acc):
    """Рекурсивно обходит дерево секций PUG-View, собирая значения нужных заголовков."""
    head = section.get("TOCHeading")
    if head in want:
        key = HEADINGS[head]
        for info in section.get("Information", []) or []:
            ref = refs.get(info.get("ReferenceNumber"), "PubChem")
            for s in _strings_from_info(info):
                acc.setdefault(key, [])
                # дедуп по (value, source)
                if not any(e["value"] == s and e["source"] == ref for e in acc[key]):
                    acc[key].append({"value": s, "source": ref})
    for sub in section.get("Section", []) or []:
        _walk(sub, want, refs, acc)


def _physchem(cid):
    b = _get(f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON/")
    if not b:
        return None
    try:
        rec = json.loads(b)["Record"]
    except Exception:
        return None
    refs = _ref_map(rec)
    acc = {}
    for sec in rec.get("Section", []) or []:
        _walk(sec, _WANT, refs, acc)
    # ограничим число вариантов на свойство (защита от мусора), сохранив провенанс
    for k in acc:
        acc[k] = acc[k][:6]
    return acc or None


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
        time.sleep(0.22)
        props = _physchem(cid) if cid else None
        if props:
            out[cas] = {"cid": cid, "props": props,
                        "source": "PubChem Experimental Properties (NIH, public domain)",
                        "needs_review": True}
            found += 1
            if found % 20 == 0:
                out["_meta"] = {"source": "PubChem physchem (NIH)", "count": found}
                json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
                got = sorted(props.keys())
                print(f"[{i}/{len(items)}] найдено {found} (последний {cas}: {got})", flush=True)
        else:
            out[cas] = None  # нет в PubChem — не перезапрашивать
        time.sleep(0.18)
    real = {k: v for k, v in out.items() if v and k != "_meta"}
    out["_meta"] = {"source": "PubChem Experimental Properties (NIH, public domain)", "count": len(real),
                    "fields": [v for v in HEADINGS.values() if v],
                    "disclaimer": "Сырые значения физхим-свойств из PubChem (агрегат справочников). "
                                  "Несколько значений = разные источники/единицы, выбор за экспертом. needs_review."}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n✓ {len(real)} веществ с физхимией из PubChem → {OUT}")


if __name__ == "__main__":
    main()
