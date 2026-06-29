# -*- coding: utf-8 -*-
"""
ПРЕДВАРИТЕЛЬНЫЙ расчёт класса опасности ОТХОДА (I–V) по Приказу Минприроды России
№ 536 от 04.12.2014 («Критерии отнесения отходов к I–V классам опасности по степени
негативного воздействия на окружающую среду»).

ЧТО ЭТО. Изолированный модуль поверх данных HEFEST. По введённому СОСТАВУ отхода
(компоненты + их массовые доли) применяет РАСЧЁТНУЮ формулу приказа 536:

        Ki = Ci / Wi ;        K = Σ Ki ,

где Ci — концентрация компонента в отходе (мг/кг отхода), Wi — коэффициент степени
опасности компонента для окружающей среды, выводимый из ПЕРВИЧНЫХ показателей опасности
компонента (ПДК, ЛД50, ЛК50, КВИО, растворимость, биоаккумуляция и т.д.) по приказу.
Итоговый класс — по диапазонам K (см. CLASS_FROM_K ниже).

⚠ СВЯТОЕ ПРАВИЛО (safety-critical). Модуль НИЧЕГО не выдумывает:
  * Wi НЕ вычисляется, пока не получены БАЛЛЫ первичных показателей. Балл (1..4) берётся
    из таблицы приказа 536 (диапазон значения показателя → балл). Эта таблица — нормативные
    числа; пока она не загружена из официального текста приказа (SCORING_TABLE_536 is None),
    score() возвращает None ⇒ Wi = «нет данных» ⇒ K и класс = «не определён». Это сделано
    НАМЕРЕННО: лучше честно отказать, чем выдать неверный класс.
  * ЛД50 в базе HEFEST ОТСУТСТВУЕТ; ПДКп (почва) тоже нет; ПДКрз есть у ~97%, ПДКв (вода)
    ~44%. Поэтому для реальных компонентов первичных показателей объективно НЕ ХВАТАЕТ —
    модуль помечает «условный / нет данных по показателю X», а не додумывает число.
  * Конкретный КОД ФККО и ОКОНЧАТЕЛЬНЫЙ класс отхода модуль НЕ присваивает — это делает
    эколог предприятия (как уже зафиксировано в waste.py). Итог всегда needs_review.

ЧТОБЫ РАСЧЁТ СТАЛ ПОЛНЫМ — догрузить (см. BLOCKERS внизу файла и /waste/estimate ответ):
  1) Таблицу баллов первичных показателей приказа 536 (диапазоны значений → балл 1..4).
  2) Балл показателя информационного обеспечения (число известных показателей n → балл).
  3) Сами первичные показатели по компонентам: ЛД50, ЛК50, КВИО, ПДКп(почва), ПДКпп,
     раств./летучесть, БД, биоаккумуляцию, персистентность — которых в базе нет.
Пока всё это не загружено — модуль детерминированно возвращает honest-gap.
"""
import os
import json
import math

FRAMEWORK_REF = "Приказ Минприроды России № 536 от 04.12.2014"

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


# ---------------------------------------------------------------------------------------------------
# Первичные показатели опасности компонента (по приказу 536, приложение).
# Это НАЗВАНИЯ показателей методики — не значения. Поле `source` указывает, есть ли в базе HEFEST
# первичные данные по этому показателю. Где None — данных нет, показатель честно помечается missing.
# Точный полный перечень и единицы — сверить с официальным текстом приказа при загрузке методики.
# ---------------------------------------------------------------------------------------------------
PRIMARY_INDICATORS = [
    {"key": "pdk_p",       "label": "ПДКп (ОДК) — почва, мг/кг",                       "source": None},
    {"key": "pdk_v",       "label": "ПДКв (ОДУ) — вода хоз.-питьевая, мг/л",            "source": "water"},
    {"key": "pdk_rz",      "label": "ПДКрз — воздух рабочей зоны, мг/м³",               "source": "subs"},
    {"key": "pdk_ss",      "label": "ПДКсс/ПДКмр (ОБУВ) — атм. воздух нас. мест, мг/м³", "source": "atmo"},
    {"key": "pdk_pp",      "label": "ПДКпп — продукты питания, мг/кг",                  "source": None},
    {"key": "ld50",        "label": "ЛД50 — мг/кг",                                     "source": None},
    {"key": "lc50",        "label": "ЛК50 — мг/м³",                                     "source": None},
    {"key": "kvio",        "label": "КВИО (коэф. возможности ингаляц. отравления)",      "source": None},
    {"key": "lg_s",        "label": "lg(S, растворимость в воде, мг/л)",                "source": None},
    {"key": "lg_cnas",     "label": "lg(Cнас, насыщающая концентрация, мг/м³)",         "source": None},
    {"key": "bd",          "label": "БД = БПК5/ХПК·100% (биоразлагаемость)",            "source": None},
    {"key": "bioaccum",    "label": "Биоаккумуляция (lg Kow / BCF)",                    "source": None},
    {"key": "persistence", "label": "Персистентность (трансформация в среде)",          "source": None},
]


# ---------------------------------------------------------------------------------------------------
# ⚠ ТАБЛИЦА БАЛЛОВ ПРИКАЗА 536 — НЕ ЗАГРУЖЕНА.
# Это нормативные числа (диапазоны значения каждого показателя → балл 1..4). Их НЕЛЬЗЯ писать
# «из головы» (святое правило). Пока None — score() всегда возвращает None, и расчёт честно
# отказывает. Чтобы включить расчёт — загрузить таблицу из официального текста приказа.
# ---------------------------------------------------------------------------------------------------
SCORING_TABLE_536 = None  # TODO: загрузить data/order_536_scoring.json (диапазоны → балл) из приказа


def score(indicator_key, value):
    """Балл (1..4) первичного показателя по таблице приказа 536, либо None если посчитать нельзя.

    Намеренно возвращает None, пока SCORING_TABLE_536 не загружена из официального текста приказа:
    диапазоны «значение → балл» — нормативные числа, их выдумывать нельзя (святое правило)."""
    if SCORING_TABLE_536 is None or value is None:
        return None
    # TODO: когда таблица загружена — найти диапазон для indicator_key и вернуть балл 1..4.
    return None  # pragma: no cover — недостижимо, пока таблица не загружена


# ---------------------------------------------------------------------------------------------------
# Расчётные соотношения приказа 536 (математика методики; применяются ТОЛЬКО при наличии баллов).
# Сверить с официальным текстом приказа при загрузке полной методики.
# ---------------------------------------------------------------------------------------------------
def z_from_x(xi):
    """Коэффициент степени опасности Zi из относительного параметра Xi: Zi = 4·Xi/3 − 1/3."""
    return 4.0 * xi / 3.0 - 1.0 / 3.0


def wi_from_z(zi):
    """Унифицированный коэффициент Wi из Zi (кусочно-логарифмическая зависимость приказа 536)."""
    if 1.0 <= zi < 2.0:
        lg_w = 4.0 - 4.0 / zi
    elif 2.0 <= zi <= 4.0:
        lg_w = zi
    elif 4.0 < zi <= 5.0:
        lg_w = 2.0 + 4.0 / (6.0 - zi)
    else:
        return None
    return 10.0 ** lg_w


# Диапазоны итогового показателя K → класс отхода (приказ 536). Применяется ТОЛЬКО когда K посчитан.
def class_from_k(k):
    """Класс отхода I–V по значению K (Σ Ci/Wi), либо None если вне диапазонов."""
    if k is None:
        return None
    if 1e4 < k <= 1e6:
        return "I"
    if 1e3 < k <= 1e4:
        return "II"
    if 1e2 < k <= 1e3:
        return "III"
    if 1e1 < k <= 1e2:
        return "IV"
    if 0 <= k <= 1e1:
        return "V"
    return None


# ---------------------------------------------------------------------------------------------------
# Доступ к данным HEFEST: индекс веществ + экологические ПДК (переиспользуем sanpin_env).
# ---------------------------------------------------------------------------------------------------
_SUBS_INDEX = None


def _subs_index():
    """Ленивый индекс веществ {name.lower() | cas -> запись} из SUBS_FILE (по умолчанию clean)."""
    global _SUBS_INDEX
    if _SUBS_INDEX is None:
        fname = os.getenv("SUBS_FILE", "substances_clean.json")
        path = fname if os.path.isabs(fname) else os.path.join(_DATA, fname)
        idx = {}
        try:
            with open(path, encoding="utf-8") as f:
                for rec in json.load(f):
                    if rec.get("name"):
                        idx[rec["name"].strip().lower()] = rec
                    if rec.get("cas"):
                        idx.setdefault(rec["cas"].strip(), rec)
        except (OSError, ValueError):
            idx = {}
        _SUBS_INDEX = idx
    return _SUBS_INDEX


def _find_substance(query):
    """Запись вещества по имени или CAS (без выдумывания: только точное совпадение по индексу)."""
    if not query:
        return None
    idx = _subs_index()
    return idx.get(str(query).strip().lower()) or idx.get(str(query).strip())


def _fetch_value(indicator, rec):
    """Первичное значение показателя для вещества: (value, units, source_label) или (None, .., None).

    Возвращает СЫРОЕ значение из базы (число/строку «как в источнике») — не пересчитываем."""
    src = indicator["source"]
    if src is None:
        return None, None, None  # показателя нет в базе HEFEST
    if src == "subs":  # ПДКрз
        v = rec.get("pdk_mgm3")
        return (v, "мг/м³", "substances_clean.json (ПДКрз)") if v not in (None, "") else (None, None, None)
    # экологические ПДК — через существующий sanpin_env (СанПиН 1.2.3685-21)
    try:
        import sanpin_env
    except ImportError:
        return None, None, None
    cas, name = rec.get("cas"), rec.get("name")
    if src == "water":
        w = sanpin_env.water_for(cas, name)
        if w and w.get("pdk"):
            return w["pdk"], "мг/л", w.get("source", "СанПиН 1.2.3685-21 (вода)")
    elif src == "atmo":
        a = sanpin_env.atmo_for(cas, name)
        if a:
            v = a.get("pdk_ss") or a.get("pdk_mr")
            if v:
                return v, "мг/м³", a.get("source", "СанПиН 1.2.3685-21 (атм. воздух)")
    return None, None, None


# ---------------------------------------------------------------------------------------------------
# Главная функция.
# ---------------------------------------------------------------------------------------------------
def estimate_waste_class(components):
    """Предварительный расчёт класса опасности отхода по приказу 536 — с ЧЕСТНЫМИ пропусками.

    Вход:  components = [{"substance": <имя|CAS>, "Ci_fraction": <0..1 массовая доля>}, ...]
    Выход: {
        class, confidence, K, per_component:[...], missing_overall:[...],
        components_total, fraction_sum, note, needs_review, framework_ref, blockers:[...]
    }
    Детерминированно. Пока не загружена таблица баллов приказа 536 и первичные показатели
    (ЛД50 и пр.) — class=None, K=None, honest-gap по каждому компоненту."""
    components = components or []
    per_component = []
    missing_overall = set()

    fraction_sum = 0.0
    for c in components:
        try:
            frac = float(c.get("Ci_fraction"))
        except (TypeError, ValueError):
            frac = None
        if frac is not None:
            fraction_sum += frac

    for c in components:
        query = (c.get("substance") or "").strip()
        try:
            frac = float(c.get("Ci_fraction"))
        except (TypeError, ValueError):
            frac = None
        ci_mg_kg = round(frac * 1_000_000, 3) if frac is not None else None  # доля → мг/кг отхода

        rec = _find_substance(query)
        if not rec:
            for ind in PRIMARY_INDICATORS:
                missing_overall.add(ind["label"])
            per_component.append({
                "substance": query, "matched": False,
                "ci_fraction": frac, "ci_mg_kg": ci_mg_kg,
                "used_indicators": [], "scored": False,
                "missing": [ind["label"] for ind in PRIMARY_INDICATORS],
                "wi": "нет данных", "ki": None,
                "reason": "вещество не найдено в базе HEFEST — первичные показатели недоступны",
            })
            continue

        used, missing, scores = [], [], []
        for ind in PRIMARY_INDICATORS:
            value, units, source_label = _fetch_value(ind, rec)
            if value in (None, ""):
                missing.append(ind["label"])
                missing_overall.add(ind["label"])
                continue
            b = score(ind["key"], value)  # балл по таблице приказа — None, пока таблица не загружена
            if b is not None:
                scores.append(b)
            used.append({
                "indicator": ind["label"], "value": value, "units": units,
                "source": source_label, "scored": b is not None,
            })

        # Wi считается ТОЛЬКО когда есть баллы по достаточному набору показателей (методика приказа).
        # Пока score() возвращает None — scores пуст ⇒ Xi/Zi/Wi не определены ⇒ honest-gap.
        wi = "нет данных"
        ki = None
        if scores and SCORING_TABLE_536 is not None:
            xi = sum(scores) / len(scores)
            zi = z_from_x(xi)
            w = wi_from_z(zi)
            if w:
                wi = w
                if ci_mg_kg is not None:
                    ki = ci_mg_kg / w

        per_component.append({
            "substance": rec.get("name", query), "cas": rec.get("cas"), "matched": True,
            "ci_fraction": frac, "ci_mg_kg": ci_mg_kg,
            "used_indicators": used, "scored": bool(scores),
            "missing": missing,
            "wi": wi, "ki": ki,
            "reason": None if (scores and SCORING_TABLE_536 is not None)
                      else "недостаточно подтверждённых показателей для коэффициента Wi "
                           "(таблица баллов приказа 536 не загружена и/или нет ЛД50/ПДКп)",
        })

    # Итог K и класс — только если ВСЕ компоненты дали Ki (методика суммирует по всем компонентам).
    kis = [pc["ki"] for pc in per_component]
    can_total = bool(per_component) and all(k is not None for k in kis)
    K = round(sum(kis), 3) if can_total else None
    waste_class = class_from_k(K) if can_total else None
    confidence = "calculated" if waste_class else "insufficient_data"

    note = (
        "ПРЕДВАРИТЕЛЬНО, требует проверки эколога. Класс НЕ определён: не хватает первичных "
        "показателей и не загружена таблица баллов приказа 536 — см. blockers/missing_overall. "
        "Числа из источников НЕ пересчитывались. Код ФККО и окончательный класс присваивает "
        "эколог предприятия (приказ 536, 89-ФЗ)."
        if waste_class is None else
        "ПРЕДВАРИТЕЛЬНЫЙ расчёт по приказу 536. Требует проверки эколога: код ФККО и "
        "окончательный класс отхода присваивает эколог предприятия."
    )

    if abs(fraction_sum - 1.0) > 0.01 and components:
        note += (f" Внимание: сумма долей компонентов = {round(fraction_sum, 4)} (не равна 1) — "
                 "проверьте состав; недостающую долю обычно составляет нетоксичная матрица/влага.")

    return {
        "class": waste_class,
        "confidence": confidence,
        "K": K,
        "components_total": len(per_component),
        "fraction_sum": round(fraction_sum, 6),
        "per_component": per_component,
        "missing_overall": sorted(missing_overall),
        "blockers": BLOCKERS,
        "scale": "I–V (классы опасности ОТХОДА; отдельная шкала от класса вещества 1–4 по ГОСТ 12.1.007)",
        "formula": "Ki = Ci / Wi ; K = Σ Ki ; класс — по диапазонам K (приказ 536)",
        "note": note,
        "needs_review": True,
        "framework_ref": FRAMEWORK_REF,
    }


# ---------------------------------------------------------------------------------------------------
# BLOCKERS — что догрузить, чтобы расчёт стал ПОЛНЫМ (а не honest-gap). Видно и в ответе API.
# ---------------------------------------------------------------------------------------------------
BLOCKERS = [
    "Таблица баллов первичных показателей приказа 536 (диапазоны значения показателя → балл 1..4) — "
    "нормативные числа, грузить из официального текста приказа в SCORING_TABLE_536. БЕЗ НЕЁ Wi не считается.",
    "Балл показателя информационного обеспечения (число известных показателей n → балл) — из приказа 536.",
    "ЛД50 (мг/кг) — в базе HEFEST ОТСУТСТВУЕТ полностью; ключевой токсикологический показатель методики.",
    "ПДКп (почва) и ОДК — нет в базе (sanpin_water — это ПДК ВОДЫ, не почвы).",
    "ЛК50, КВИО, ПДКпп (продукты питания), растворимость/летучесть (lg S, lg Cнас), БД (БПК5/ХПК), "
    "биоаккумуляция (lg Kow / BCF), персистентность — первичных значений по компонентам нет.",
    "Точный полный перечень первичных показателей и формула усреднения Xi — сверить с приложением приказа 536.",
]


if __name__ == "__main__":
    # Детерминированная самопроверка. Ожидаем honest-gap: класс не определён, всё needs_review,
    # ЛД50 числится в пропусках, ПДКрз (если вещество в базе) попадает в used_indicators.
    sample = [
        {"substance": "серная кислота", "Ci_fraction": 0.6},
        {"substance": "аммиак", "Ci_fraction": 0.3},
        {"substance": "несуществующее вещество X", "Ci_fraction": 0.1},
    ]
    res = estimate_waste_class(sample)

    print("=== САМОПРОВЕРКА waste_calc (приказ 536) ===")
    print("class                :", res["class"])
    print("confidence           :", res["confidence"])
    print("K                    :", res["K"])
    print("needs_review         :", res["needs_review"])
    print("framework_ref        :", res["framework_ref"])
    print("fraction_sum         :", res["fraction_sum"])
    print("components_total     :", res["components_total"])
    for pc in res["per_component"]:
        used = ", ".join(u["indicator"].split(" —")[0] + "=" + str(u["value"]) for u in pc["used_indicators"]) or "—"
        print(f"  • {pc['substance']:<28} matched={pc['matched']!s:<5} wi={pc['wi']!s:<10} "
              f"used[{used}] missing={len(pc['missing'])}")
    print("missing_overall (всего %d):" % len(res["missing_overall"]))
    for m in res["missing_overall"]:
        print("   -", m)
    print("blockers (%d):" % len(res["blockers"]))
    for b in res["blockers"]:
        print("   -", b)

    # --- assertions (детерминированно) ---
    assert res["class"] is None, "класс ДОЛЖЕН быть None (honest-gap), пока нет таблицы баллов/ЛД50"
    assert res["K"] is None, "K должен быть None"
    assert res["confidence"] == "insufficient_data"
    assert res["needs_review"] is True
    assert res["framework_ref"] == FRAMEWORK_REF
    assert any("ЛД50" in m for m in res["missing_overall"]), "ЛД50 обязан числиться в пропусках"
    assert all(pc["wi"] == "нет данных" for pc in res["per_component"]), "Wi нигде не выдуман"
    # вещество из базы должно отдать хотя бы ПДКрз как найденный (но НЕscored) показатель
    h2so4 = next(pc for pc in res["per_component"] if pc["matched"])
    assert any("ПДКрз" in u["indicator"] for u in h2so4["used_indicators"]), "ПДКрз должен найтись"
    assert all(not u["scored"] for u in h2so4["used_indicators"]), "ни один показатель не должен быть scored"
    # ненайденное вещество — корректный honest-gap
    miss = next(pc for pc in res["per_component"] if not pc["matched"])
    assert miss["wi"] == "нет данных" and miss["used_indicators"] == []
    # математика методики корректна на синтетике (проверяем формулы, не выдумывая нормативку):
    assert class_from_k(5e4) == "I" and class_from_k(50) == "IV" and class_from_k(5) == "V"
    assert wi_from_z(3.0) is not None and abs(math.log10(wi_from_z(3.0)) - 3.0) < 1e-9
    print("\nOK: самопроверка пройдена — honest-gap соблюдён, нормативка не выдумана.")
