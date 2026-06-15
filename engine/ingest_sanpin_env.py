# -*- coding: utf-8 -*-
"""
Парсинг экологических ПДК из СанПиН 1.2.3685-21 (DOCX, разбитый источником на части):
  - АТМОСФЕРА населённых мест — Часть 1, Таблица 1.1  -> data/sanpin_atmo.json
  - ВОДА водных объектов        — Часть 3, Таблица 12  -> data/sanpin_water.json

Источник значений — официальный нормативный акт РФ (Постановление Главного государственного санитарного
врача РФ № 2 от 28.01.2021). По ст. 1259 п. 6 ГК РФ официальные документы госорганов авторским правом
НЕ охраняются — значения можно переиспользовать с указанием провенанса. Сторонний хостинг копии DOCX
на нормативную ценность не влияет (важен сам акт, а не носитель).

ПРИНЦИП БЕЗОПАСНОСТИ: значения берутся из таблицы КАК ЕСТЬ. Десятичная запятая и пометки (напр. «(к)» —
канцероген) сохраняются в сыром виде (`*_raw`), а float пишем ТОЛЬКО если значение — одиночное число.
Ничего не выдумываем и не пересчитываем; всё needs_review. Строки «Выброс запрещён» помечаем флагом.

Запуск:  python3 engine/ingest_sanpin_env.py
"""
import os, re, json, docx

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
SRC = os.path.join(DATA, "sources", "sanpin_1.2.3685-21.docx")    # Часть 1 (атмосфера)
SRC_WATER = os.path.join(DATA, "sources", "sanpin_part3.docx")     # Часть 3 (вода)
OUT = os.path.join(DATA, "sanpin_atmo.json")
OUT_WATER = os.path.join(DATA, "sanpin_water.json")

_NUM = re.compile(r"^\d+\.$")            # '1.' — строка данных (не '1'..'9' — нумерация колонок)
_CAS = re.compile(r"^\d{2,7}-\d{2}-\d$")  # формат CAS
_LEADNUM = re.compile(r"^[\d,\.]+")       # ведущее число для значений с пометками («0,0001 (к)»)


def _f(s):
    """Ведущее одиночное число '0,001'/'0,0001 (к)' -> float. Иначе None (храним только сырое)."""
    s = (s or "").strip().replace("\xa0", " ").replace("\n", " ")
    if not s:
        return None
    m = _LEADNUM.match(s.replace(" ", ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "."))
    except ValueError:
        return None


def _cell(row, i):
    return row.cells[i].text.strip().replace("\xa0", " ") if i < len(row.cells) else ""


def _clean(s):
    """Схлопывает переносы/пробелы в одну строку (имена/значения из ячеек с \\n)."""
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def parse_water():
    """Часть 3, Таблица 12 — ПДК воды (мг/л). Колонки: №|name|CAS|формула|ПДК|ЛПВ|класс."""
    d = docx.Document(SRC_WATER)
    t = d.tables[12]
    by_cas, by_name = {}, {}
    n = 0
    for row in t.rows:
        if not _NUM.match(_cell(row, 0)):
            continue
        name = _clean(_cell(row, 1))
        cas = _cell(row, 2)
        pdk = _clean(_cell(row, 4))
        lpv = _clean(_cell(row, 5))
        hcls = _clean(_cell(row, 6))
        if not name or not pdk:
            continue
        rec = {
            "name": name, "norm_type": "ПДК", "cas": cas if _CAS.match(cas) else None,
            "pdk_raw": pdk, "pdk": _f(pdk), "lpv": lpv or None,
            "hazard_class": hcls or None,
            "source": "СанПиН 1.2.3685-21, Табл. 3.13 (ПДК воды водных объектов хоз.-питьевого/культ.-бытового)",
            "needs_review": True,
        }
        n += 1
        by_name[name.lower()] = rec
        if rec["cas"]:
            by_cas[rec["cas"]] = rec

    # ОДУ воды (Часть 3, табл. [13]) — ориентировочные допустимые уровни для веществ БЕЗ ПДК.
    n_odu = 0
    for row in d.tables[13].rows:
        if not _NUM.match(_cell(row, 0)):
            continue
        name = _clean(_cell(row, 1)); cas = _cell(row, 2)
        odu = _clean(_cell(row, 4)); lpv = _clean(_cell(row, 5)); hcls = _clean(_cell(row, 6))
        if not name or not odu:
            continue
        nm = name.lower(); cas_v = cas if _CAS.match(cas) else None
        if nm in by_name or (cas_v and cas_v in by_cas):    # ПДК есть -> не перетираем
            continue
        rec = {"name": name, "norm_type": "ОДУ", "cas": cas_v,
               "odu_raw": odu, "odu": _f(odu), "lpv": lpv or None, "hazard_class": hcls or None,
               "source": "СанПиН 1.2.3685-21, Табл. 3.14 (ОДУ воды водных объектов)",
               "needs_review": True}
        by_name[nm] = rec
        if cas_v:
            by_cas[cas_v] = rec
        n_odu += 1

    out = dict(by_cas)
    out["_by_name"] = by_name
    out["_meta"] = {
        "source": "СанПиН 1.2.3685-21 (Постановление ГГСВ РФ № 2 от 28.01.2021), Таблицы 3.13 (ПДК) и 3.14 (ОДУ)",
        "field": "ПДК/ОДУ воды водных объектов хоз.-питьевого и культурно-бытового водопользования (мг/л)",
        "legal": "Официальный нормативный акт РФ — ст. 1259 п. 6 ГК РФ (не охраняется авторским правом).",
        "count_with_cas": len(by_cas), "count_pdk": n, "count_odu": n_odu,
        "disclaimer": "ЛПВ: с.-т.=санитарно-токсикологический, орг.=органолептический. Пометка «(к)» в ПДК — "
                      "канцероген. ОДУ — ориентировочный уровень (слабее ПДК). Значения из официального акта, needs_review.",
    }
    json.dump(out, open(OUT_WATER, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"✓ Вода: ПДК {n} + ОДУ {n_odu}, с CAS {len(by_cas)} → {OUT_WATER}")


def main():
    d = docx.Document(SRC)
    t = d.tables[0]                       # Таблица 1.1 — ПДК атмосферного воздуха
    by_cas, by_name = {}, {}
    n_rows = n_prohib = 0
    for row in t.rows:
        c0 = _cell(row, 0)
        if not _NUM.match(c0):            # пропускаем заголовки и строку нумерации колонок
            continue
        name = _cell(row, 1)
        cas = _cell(row, 2)
        pdk_mr = _cell(row, 4)
        pdk_ss = _cell(row, 5)
        pdk_sg = _cell(row, 6)
        limit = _cell(row, 7)
        hcls = _cell(row, 8)
        if not name:
            continue
        prohibited = "запрещ" in (pdk_mr + pdk_ss + limit).lower()
        if prohibited:
            n_prohib += 1
        rec = {
            "name": name, "norm_type": "ПДК",
            "cas": cas if _CAS.match(cas) else None,
            "pdk_mr_raw": pdk_mr or None, "pdk_mr": _f(pdk_mr),
            "pdk_ss_raw": pdk_ss or None, "pdk_ss": _f(pdk_ss),
            "pdk_sg_raw": pdk_sg or None,
            "limit": limit or None,        # лимитирующий показатель (рез./рефл./рефл.-рез.)
            "hazard_class": hcls or None,
            "emission_prohibited": prohibited or None,
            "source": "СанПиН 1.2.3685-21, Табл. 1.1 (ПДК атмосферного воздуха населённых мест)",
            "needs_review": True,
        }
        n_rows += 1
        nm = name.lower()
        by_name[nm] = rec
        if rec["cas"]:
            by_cas[rec["cas"]] = rec

    # ОБУВ атмосферы (Часть 1, табл. [1]) — ориентировочно безопасные уровни для веществ БЕЗ ПДК.
    # Слабее ПДК по статусу. Добавляем ТОЛЬКО туда, где ПДК нет (ПДК приоритетнее).
    n_obuv = 0
    for row in d.tables[1].rows:
        if not _NUM.match(_cell(row, 0)):
            continue
        name = _clean(_cell(row, 1)); cas = _cell(row, 2); obuv = _clean(_cell(row, 4))
        if not name or not obuv:
            continue
        nm = name.lower(); cas_v = cas if _CAS.match(cas) else None
        if nm in by_name or (cas_v and cas_v in by_cas):    # ПДК есть -> не перетираем
            continue
        rec = {"name": name, "norm_type": "ОБУВ", "cas": cas_v,
               "obuv_raw": obuv, "obuv": _f(obuv),
               "source": "СанПиН 1.2.3685-21, Табл. 1.2 (ОБУВ атмосферного воздуха населённых мест)",
               "needs_review": True}
        by_name[nm] = rec
        if cas_v:
            by_cas[cas_v] = rec
        n_obuv += 1
    out = dict(by_cas)
    out["_by_name"] = by_name
    out["_meta"] = {
        "source": "СанПиН 1.2.3685-21 (Постановление ГГСВ РФ № 2 от 28.01.2021), Таблица 1.1",
        "field": "ПДК атмосферного воздуха населённых мест (мг/м³): макс. разовая / среднесуточная",
        "legal": "Официальный нормативный акт РФ — ст. 1259 п. 6 ГК РФ (не охраняется авторским правом).",
        "count_with_cas": len(by_cas), "count_pdk": n_rows, "count_obuv": n_obuv,
        "emission_prohibited": n_prohib,
        "disclaimer": "ПДК атмосферы (населённых мест) ≠ ПДК рабочей зоны. ОБУВ — ориентировочный уровень "
                      "(слабее ПДК), для веществ без утверждённого ПДК. Значения из официального акта, "
                      "needs_review; сверяйте с действующей редакцией (СанПиН 1.2.3685-21 до 01.03.2027).",
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"✓ Атмосфера: ПДК {n_rows} + ОБУВ {n_obuv}, с CAS {len(by_cas)}, «выброс запрещён» {n_prohib} → {OUT}")


if __name__ == "__main__":
    main()
    parse_water()
