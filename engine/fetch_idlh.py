# -*- coding: utf-8 -*-
"""
Загрузка значений IDLH (Immediately Dangerous to Life or Health) из NIOSH — авторитетного
первоисточника (cdc.gov/niosh/idlh), public domain. IDLH = острый порог: концентрация, при
которой без СИЗ человек гибнет/получает необратимый вред за ~30 мин. Дополняет наш хронический
ПДК рабочей зоны острым порогом для аварийного реагирования.

ПРИНЦИП БЕЗОПАСНОСТИ: значения НЕ вводятся вручную и НЕ генерируются — только парсятся со страницы
NIOSH по CAS, с сохранением URL-источника. Всё помечается needs_review (сверить с первоисточником).
NIOSH покрывает ~500 веществ; для отсутствующих честно ничего не пишем.

Запуск:  python3 engine/fetch_idlh.py [path_cas_json]
  path_cas_json — {имя: cas}; по умолчанию /tmp/prio_cas.json (приоритетный набор).
Результат: data/idlh.json  {cas: {idlh, units, niosh_rel, basis, source, source_url, needs_review}}
"""
import sys, os, re, json, time, urllib.request

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
OUT = os.path.join(DATA, "idlh.json")
UA = {"User-Agent": "Mozilla/5.0 (rag-sds pilot; chemical-safety research)"}


def _fetch(cas):
    nodash = cas.replace("-", "").strip()
    url = f"https://www.cdc.gov/niosh/idlh/{nodash}.html"
    try:
        req = urllib.request.Request(url, headers=UA)
        h = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
    except Exception:
        return None, url
    if "Revised IDLH" not in h and "IDLH for" not in h:
        return None, url
    rec = {"source": "NIOSH IDLH (cdc.gov/niosh/idlh)", "source_url": url, "needs_review": True}

    # Revised IDLH: <value> <units>
    m = re.search(r"Revised IDLH:\s*</strong>\s*([0-9][0-9.,]*)\s*(ppm|mg/m)", h)
    if not m:
        # запасной разбор из мета-предложения "IDLH for X is N ppm ..."
        m = re.search(r"IDLH for [^<]+? is\s*([0-9][0-9.,]*)\s*(ppm|mg/m)", h)
    if m:
        rec["idlh"] = m.group(1).replace(",", "")
        rec["units"] = "ppm" if m.group(2) == "ppm" else "mg/m³"
    else:
        # бывают нечисловые ("N.D." — не определено) — честно фиксируем
        if re.search(r"Revised IDLH:\s*</strong>\s*N\.?D", h):
            rec["idlh"] = None; rec["units"] = None; rec["note_raw"] = "NIOSH: N.D. (не определено)"
        else:
            return None, url

    # основание (acute toxicity data...) — короткая выжимка из мета-описания
    b = re.search(r'name="description" content="([^"]+)"', h)
    if b:
        rec["basis"] = re.sub(r"\s+", " ", b.group(1)).strip()[:300]

    # NIOSH REL — рекомендованный предел (для контекста)
    r = re.search(r"NIOSH REL:\s*</strong>\s*([^<]+)", h)
    if r:
        rec["niosh_rel"] = re.sub(r"\s+", " ", r.group(1)).strip()[:120]
    return rec, url


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "/tmp/prio_cas.json"
    name_cas = json.load(open(src, encoding="utf-8"))
    out = {}
    found = 0
    for i, (name, cas) in enumerate(sorted(name_cas.items()), 1):
        if not cas:
            continue
        rec, url = _fetch(cas)
        if rec:
            out[cas] = rec
            found += 1
            v = rec.get("idlh"); u = rec.get("units") or ""
            print(f"[{i:>3}] {name:<30} {cas:<12} IDLH={v} {u}")
        else:
            print(f"[{i:>3}] {name:<30} {cas:<12} — нет в NIOSH")
        time.sleep(0.4)  # вежливо к серверу
    meta = {"_meta": {"source": "NIOSH IDLH values, cdc.gov/niosh/idlh (public domain, US HHS)",
                      "fetched_count": found, "total_queried": len(name_cas),
                      "disclaimer": "Острый порог IDLH из NIOSH. Числа в ppm/мг·м⁻³ как у первоисточника. "
                                    "needs_review — сверить с cdc.gov/niosh/idlh. НЕ заменяет российские нормативы."}}
    out = {**meta, **out}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n✓ {found}/{len(name_cas)} веществ с IDLH → {OUT}")


if __name__ == "__main__":
    main()
