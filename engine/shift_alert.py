# -*- coding: utf-8 -*-
"""
РЕАКЦИЯ НА ПРЕВЫШЕНИЕ / МАСТЕР СМЕНЫ.

Газоанализатор показал превышение → мастер смены вводит вещество + измеренную концентрацию →
карточка «что делать сейчас»: идентификация, пороги (ПДКрз / IDLH), сравнение, СИЗ, действия.

⚠️ СВЯТОЕ ПРАВИЛО (safety-critical). Цена ошибки = здоровье человека. Этот модуль НИЧЕГО
не выдумывает и, ГЛАВНОЕ, **никогда не пересчитывает единицы**:
  • ПДКрз хранится у вещества в мг/м³ (поле pdk_mgm3); IDLH (NIOSH) — в своих единицах
    (для газов это ppm), как у первоисточника. ppm ↔ мг/м³ требуют молярной массы —
    мы её НЕ синтезируем и НЕ конвертируем.
  • Кратность превышения ПДК = value/ПДК считаем ТОЛЬКО когда единица введённого значения
    совпадает с единицей ПДК. Иначе кратность = None и явная причина «единицы разные».
  • Сравнение с IDLH («выше IDLH») — ТОЛЬКО когда единица значения совпадает с единицей IDLH.
  • tier/severity выводится исключительно из КОРРЕКТНОГО сравнения; при несовпадении единиц
    или отсутствии порога — «не определено», а не угадывание.
  • Чек-лист действий — общая безопасная логика реагирования (проветривание/эвакуация/СИЗ/
    изоляция источника), БЕЗ выдуманных чисел. Это инструмент-подсказка; решение и
    ответственность — за мастером смены / специалистом.
  • Где данных нет — «нет данных», не додумывать.

Изолированный новый код: переиспользует ppe.recommend_ppe (СИЗ паспорт/baseline с дисклеймером)
и, как dispatch.py, готовый результат эндпоинта /emergency (is_ahov / IDLH / ООН). service.py
НЕ редактируется.

Как зовётся из сервиса (аналогично ppe/dispatch — оркестратор подключает так):
    s, _ = _resolve_sub(name)
    if not s: return {"error": "вещество не найдено"}
    em = emergency(name)                       # результат /emergency (is_ahov, idlh, un_number)
    return shift_alert.assess_exceedance(s, value=value, unit=unit, emergency=em)
"""
import os, json

try:
    import ppe  # СИЗ: паспорт (grade=passport) или типовое по группе (grade=baseline) + дисклеймер
except ImportError:
    ppe = None

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")

# Единица ПДК рабочей зоны в нашей базе: поле называется pdk_mgm3 → всегда мг/м³.
PDK_UNIT = "мг/м³"

_PROV_PDK = "нормативная база РФ (ГН 2.2.5 / СанПиН 1.2.3685-21), ПДК рабочей зоны"
_PROV_IDLH = "NIOSH IDLH (cdc.gov/niosh/idlh), острый порог — без СИЗ опасно для жизни/здоровья"

TOOL_NOTE = ("Инструмент-подсказка для мастера смены. Сравнивает измеренное значение с порогами "
             "как они хранятся в источнике, БЕЗ пересчёта единиц. Не заменяет ПЛАС, инструкцию по "
             "рабочему месту и решение ответственного. Решение и ответственность — за мастером "
             "смены / специалистом по ПБ.")


def _load(fn, default):
    try:
        return json.load(open(os.path.join(_DATA, fn), encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return default


def _norm_unit(u):
    """Нормализовать единицу к каноническому виду для СРАВНЕНИЯ (не для пересчёта).
    Возвращает 'мг/м³' | 'ppm' | исходную строку (если не распознали) | None."""
    if u is None:
        return None
    s = str(u).strip().lower().replace(" ", "")
    s = s.replace("³", "3").replace("^3", "3").replace("·", "")
    if s in ("мг/м3", "mg/m3", "mgm3", "мгм3", "mg/м3", "мг/m3"):
        return "мг/м³"
    if s in ("ppm", "ppmv", "млн-1", "млн^-1", "частей/млн", "ppmvol"):
        return "ppm"
    return str(u).strip() or None


def _to_float(x):
    """Аккуратно привести к float (строка/запятая-десятичный/None). Возвращает None если не число."""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(",", ".")
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _local_emergency(substance):
    """Резерв, когда результат /emergency не передан (standalone / __main__).

    Собирает только то, что нужно для оценки превышения: is_ahov, IDLH-запись, ООН-номер.
    В сервисе вместо этого передаётся готовый emergency=emergency(name) — один в один логика."""
    name = (substance or {}).get("name") or ""
    key = name.lower().strip()
    ahov = _load("ahov_cards.json", {"cards": {}}).get("cards", {})
    erg = _load("erg_ahov.json", {"cards": {}}).get("cards", {})
    idlh_all = _load("idlh.json", {})
    card = ahov.get(key)
    erec = erg.get(key)
    cas = (substance or {}).get("cas")
    irec = idlh_all.get(cas) if cas else None
    irec = irec if (irec and irec.get("idlh") is not None) else None
    return {
        "substance": name,
        "is_ahov": bool((card and card.get("ahov")) or erec),
        "un_number": (card or {}).get("un") or (erec or {}).get("un_number"),
        "idlh": irec,
        "emergency_note": (card or {}).get("note"),
    }


def _identification(sub):
    """Идентификация вещества с провенансом. Числа/метки не выдумываем — пусто = «нет данных»."""
    name = sub.get("name")
    formula = (sub.get("formula") or "").strip()
    hc = sub.get("hazard_class")
    ghs = sub.get("ghs") or []
    return {
        "name": name,
        "formula": {"value": formula, "source": "паспорт / идентификация вещества"}
                   if formula else {"value": None, "note": "нет данных"},
        "hazard_class": {"value": str(hc), "source": _PROV_PDK}
                        if hc not in (None, "") else {"value": None, "note": "нет данных"},
        "ghs": {"value": list(ghs), "source": "паспорт / классификация вещества"}
               if ghs else {"value": [], "note": "нет данных"},
    }


def _thresholds(sub, em):
    """Пороги КАК ХРАНЯТСЯ, без пересчёта. ПДК — мг/м³; IDLH — в своих единицах (для газов ppm)."""
    pdk_raw = sub.get("pdk_mgm3")
    pdk_val = _to_float(pdk_raw)
    pdk = {
        "present": pdk_raw not in (None, ""),
        "value": pdk_raw if pdk_raw not in (None, "") else None,
        "numeric": pdk_val,                 # None если ПДК в нечисловом формате (диапазон и т.п.)
        "unit": PDK_UNIT if pdk_raw not in (None, "") else None,
        "source": _PROV_PDK if pdk_raw not in (None, "") else None,
        "note": None if pdk_raw not in (None, "") else "нет данных",
    }

    irec = (em or {}).get("idlh")
    if irec and irec.get("idlh") is not None:
        idlh = {
            "present": True,
            "value": irec.get("idlh"),
            "numeric": _to_float(irec.get("idlh")),
            "unit": irec.get("units"),
            "source": _PROV_IDLH,
            "source_url": irec.get("source_url"),
            "basis": irec.get("basis"),
            "note": None,
        }
    else:
        # Нет IDLH → НЕ показываем порог (honest-gap), а не подставляем чужой.
        idlh = {"present": False, "value": None, "numeric": None, "unit": None,
                "source": None, "note": "нет данных"}
    return pdk, idlh


def _compare(measured_num, measured_unit_norm, pdk, idlh):
    """Сравнение измеренного с порогами. Кратность/«выше порога» — ТОЛЬКО при совпадении единиц.

    Возвращает (comparison_dict, severity_dict). severity выводится исключительно из корректного
    сравнения; ничего не угадываем."""
    pdk_unit_n = _norm_unit(pdk.get("unit"))
    idlh_unit_n = _norm_unit(idlh.get("unit"))

    # --- кратность ПДК ---
    pdk_ratio = None
    pdk_ratio_reason = None
    if measured_num is None:
        pdk_ratio_reason = "не введена измеренная концентрация"
    elif not pdk["present"] or pdk["numeric"] is None:
        pdk_ratio_reason = "ПДК нет в данных" if not pdk["present"] else \
            f"ПДК хранится в нечисловом формате ({pdk['value']}) — кратность не считаем"
    elif measured_unit_norm is None:
        pdk_ratio_reason = "не указана единица измеренного значения"
    elif measured_unit_norm != pdk_unit_n:
        pdk_ratio_reason = (f"единицы разные: измерено в «{measured_unit_norm}», ПДК в «{pdk['unit']}» — "
                            f"не пересчитываем, сверьте вручную")
    else:
        denom = pdk["numeric"]
        pdk_ratio = round(measured_num / denom, 2) if denom else None
        if denom == 0:
            pdk_ratio_reason = "ПДК = 0 в данных — кратность не определена"

    pdk_comparable = pdk_ratio is not None
    pdk_exceeded = (pdk_comparable and pdk_ratio is not None and measured_num > pdk["numeric"]) \
        if pdk_comparable else None

    # --- сравнение с IDLH ---
    idlh_comparable = False
    idlh_exceeded = None
    idlh_reason = None
    if not idlh["present"]:
        idlh_reason = "IDLH нет в данных"
    elif measured_num is None:
        idlh_reason = "не введена измеренная концентрация"
    elif idlh["numeric"] is None:
        idlh_reason = "IDLH в нечисловом формате — не сравниваем"
    elif measured_unit_norm is None:
        idlh_reason = "не указана единица измеренного значения"
    elif measured_unit_norm != idlh_unit_n:
        idlh_reason = (f"единицы разные: измерено в «{measured_unit_norm}», IDLH в «{idlh['unit']}» — "
                       f"не пересчитываем, сверьте вручную")
    else:
        idlh_comparable = True
        idlh_exceeded = measured_num >= idlh["numeric"]

    comparison = {
        "pdk_ratio": pdk_ratio,                 # value/ПДК или None
        "pdk_comparable": pdk_comparable,
        "pdk_exceeded": pdk_exceeded,
        "pdk_ratio_reason": pdk_ratio_reason,   # почему не посчитали (если не посчитали)
        "idlh_comparable": idlh_comparable,
        "idlh_exceeded": idlh_exceeded,
        "idlh_reason": idlh_reason,
        "units_match_pdk": (measured_unit_norm is not None and measured_unit_norm == pdk_unit_n),
        "units_match_idlh": (measured_unit_norm is not None and measured_unit_norm == idlh_unit_n),
    }

    # --- severity / tier (строго из корректного сравнения) ---
    # level: 0 ниже ПДК · 1 выше ПДК · 2 выше IDLH · -1 не определено
    if idlh_comparable and idlh_exceeded:
        sev = ("above_idlh", "Выше IDLH — острый порог опасности для жизни/здоровья", 2,
               f"измерено {measured_num} {idlh['unit']} ≥ IDLH {idlh['value']} {idlh['unit']} (единицы совпадают)")
    elif pdk_comparable and pdk_exceeded:
        sev = ("above_pdk", "Выше ПДК рабочей зоны", 1,
               f"измерено {measured_num} {pdk['unit']} > ПДК {pdk['value']} {pdk['unit']} (единицы совпадают)")
    elif pdk_comparable and not pdk_exceeded:
        sev = ("below_pdk", "В пределах ПДК (не выше)", 0,
               f"измерено {measured_num} {pdk['unit']} ≤ ПДК {pdk['value']} {pdk['unit']} (единицы совпадают)")
    else:
        # ни одно корректное сравнение невозможно — честно «не определено», без угадывания
        why = pdk_ratio_reason or idlh_reason or "недостаточно данных для сравнения"
        sev = ("undetermined", "Не определено (нет порога или единицы разные)", -1, why)

    severity = {"code": sev[0], "label": sev[1], "level": sev[2], "basis": sev[3]}
    return comparison, severity


# Чек-листы действий по tier. ОБЩАЯ безопасная логика реагирования — БЕЗ выдуманных чисел.
_ACTIONS = {
    "above_idlh": [
        "Немедленно вывести людей из зоны; вход в зону — ТОЛЬКО в изолирующем СИЗОД (автономный дыхательный аппарат).",
        "Объявить тревогу по регламенту объекта; вызвать газоспасательную службу / ПАСФ и медслужбу.",
        "Перекрыть/изолировать источник выброса дистанционно, если это безопасно; остановить процесс по инструкции.",
        "Организовать учёт людей, перекличку; пострадавших — на свежий воздух (спасатель в СИЗОД), первая помощь по карточке.",
        "Усилить проветривание/осаждение по инструкции объекта; не возвращать людей до снятия превышения замером.",
    ],
    "above_pdk": [
        "Применить СИЗ органов дыхания и кожи по карточке вещества; ограничить доступ в зону.",
        "Усилить вентиляцию/проветривание; по возможности найти и изолировать источник выделения.",
        "Продолжать контроль газоанализатором; следить за динамикой (рост → действовать как при более высоком уровне).",
        "Оповестить мастера смены / ответственного по ПБ; зафиксировать событие и время.",
        "Не допускать работ без СИЗ в зоне до возврата концентрации в пределы ПДК (подтвердить замером).",
    ],
    "below_pdk": [
        "Превышения ПДК по замеру нет — продолжать штатный контроль газоанализатором.",
        "Поддерживать штатную вентиляцию; проверить исправность/калибровку газоанализатора при сомнениях.",
        "Зафиксировать замер; при росте показаний повторить оценку.",
    ],
    "undetermined": [
        "Степень опасности по замеру НЕ определена (нет порога в данных или единицы измерения разные).",
        "НЕ пересчитывать единицы самостоятельно — сверить единицу газоанализатора с единицей порога вручную / со специалистом.",
        "До прояснения действовать по принципу предосторожности: СИЗ органов дыхания, ограничить доступ, проветривание.",
        "Привлечь специалиста по ПБ; свериться с паспортом безопасности и инструкцией рабочего места.",
    ],
}
_ACTION_DISCLAIMER = ("Чек-лист — общая безопасная логика реагирования (без нормативных чисел). "
                      "Порядок и достаточность мер определяет мастер смены / специалист по ПБ по "
                      "ПЛАС и инструкциям объекта. Решение и ответственность — за человеком.")


def _ppe_block(sub):
    """СИЗ через ppe.recommend_ppe — паспорт (grade=passport) или типовое по группе (baseline)."""
    if ppe is None:
        return {"available": False, "note": "модуль СИЗ недоступен — см. /ppe и паспорт вещества"}
    r = ppe.recommend_ppe(sub)
    return {
        "available": True,
        "value": r["ppe"]["value"],
        "grade": r["ppe"]["grade"],            # passport | baseline
        "source": r["ppe"]["source"],
        "disclaimer": r["ppe"]["disclaimer"],  # not None только для baseline
        "categories": r["categories"],
        "category_labels": r["category_labels"],
    }


def assess_exceedance(substance, value=None, unit=None, emergency=None):
    """Оценка реакции на превышение для мастера смены.

    substance — словарь вещества (как у ppe.recommend_ppe: объект из SUBS/_resolve_sub);
    value     — измеренное значение (число/строка; опц. — без него только идентификация+пороги);
    unit      — единица измеренного значения, как ввёл пользователь ('мг/м³' | 'ppm' | …);
    emergency — готовый результат эндпоинта /emergency (is_ahov, idlh, un_number); если None —
                собирается локально (для standalone/__main__).

    Детерминированно. Единицы НЕ пересчитываются. Возвращает структурированный dict.
    """
    if not substance:
        return {"error": "вещество не найдено"}

    em = emergency if emergency is not None else _local_emergency(substance)
    name = substance.get("name") or em.get("substance")

    measured_num = _to_float(value)
    measured_unit_norm = _norm_unit(unit)
    measured = {
        "present": measured_num is not None,
        "value": measured_num,
        "raw_value": value,
        "unit": (unit.strip() if isinstance(unit, str) else unit) if measured_unit_norm else None,
        "unit_normalized": measured_unit_norm,
        "note": None if measured_num is not None else "значение не введено",
    }

    pdk, idlh = _thresholds(substance, em)
    comparison, severity = _compare(measured_num, measured_unit_norm, pdk, idlh)

    is_ahov = bool((em or {}).get("is_ahov"))
    ahov = {
        "is_ahov": is_ahov,
        "substance": name,
        "un_number": (em or {}).get("un_number"),
        "note": ("Вещество отнесено к АХОВ → при утечке с массой выброса разверните оперативную "
                 "карточку диспетчера (зона заражения). Зону здесь НЕ считаем — нет массы выброса."
                 if is_ahov else None),
        "dispatch_link": f"/dispatch.html?name={name}" if (is_ahov and name) else None,
    }

    return {
        "substance": name,
        "tool_note": TOOL_NOTE,
        "identification": _identification(substance),
        "measured": measured,
        "thresholds": {"pdk": pdk, "idlh": idlh},
        "comparison": comparison,
        "severity": severity,
        "ppe": _ppe_block(substance),
        "ahov": ahov,
        "actions": {
            "tier": severity["code"],
            "items": list(_ACTIONS[severity["code"]]),
            "disclaimer": _ACTION_DISCLAIMER,
        },
        "confidence": "needs_review",
    }


if __name__ == "__main__":
    # Самопроверка: детерминированный прогон без сети (локальный emergency).
    subs = {s["name"].lower(): s
            for s in _load("substances_clean.json", [])} if isinstance(
        _load("substances_clean.json", []), list) else {}

    def pick(*names):
        for n in names:
            if n.lower() in subs:
                return subs[n.lower()]
            for k, v in subs.items():
                if n.lower() in k:
                    return v
        return None

    def show(tag, r):
        sev = r["severity"]; cmp = r["comparison"]; th = r["thresholds"]
        print(f"\n[{tag}] {r['substance']}  АХОВ={r['ahov']['is_ahov']}")
        print(f"  измерено: {r['measured']['raw_value']} {r['measured']['unit']} "
              f"(норм. {r['measured']['unit_normalized']})")
        print(f"  ПДК: {th['pdk']['value']} {th['pdk']['unit']}  |  "
              f"IDLH: {th['idlh']['value']} {th['idlh']['unit']}")
        print(f"  кратность ПДК: {cmp['pdk_ratio']}  (reason: {cmp['pdk_ratio_reason']})")
        print(f"  IDLH сравнимо: {cmp['idlh_comparable']} превышен: {cmp['idlh_exceeded']} "
              f"(reason: {cmp['idlh_reason']})")
        print(f"  SEVERITY: [{sev['level']}] {sev['code']} — {sev['label']}")
        print(f"            basis: {sev['basis']}")
        print(f"  СИЗ grade: {r['ppe'].get('grade')}")

    cl = pick("хлор")
    show("хлор 3 мг/м³ (выше ПДК 1)", assess_exceedance(cl, value=3, unit="мг/м³"))
    show("хлор 0.5 мг/м³ (ниже ПДК)", assess_exceedance(cl, value=0.5, unit="мг/м³"))
    show("хлор 15 ppm (IDLH 10 ppm)", assess_exceedance(cl, value=15, unit="ppm"))
    show("метанол 100 мг/м³ (не АХОВ)", assess_exceedance(pick("метанол"), value=100, unit="мг/м³"))
    show("несовпадение единиц: хлор 5 ppm vs ПДК мг/м³",
         assess_exceedance(cl, value=5, unit="ppm"))

    # honest-gap: вещество без ПДК → severity undetermined
    no_pdk = next((s for s in subs.values() if not s.get("pdk_mgm3")), None)
    if no_pdk:
        show("без ПДК (honest-gap)", assess_exceedance(no_pdk, value=10, unit="мг/м³"))

    # Инварианты святого правила
    r_units = assess_exceedance(cl, value=5, unit="ppm")
    assert r_units["comparison"]["pdk_ratio"] is None, "ppm против ПДК мг/м³ не должно давать кратность"
    assert "единицы разные" in (r_units["comparison"]["pdk_ratio_reason"] or "")
    r_idlh = assess_exceedance(cl, value=15, unit="ppm")
    assert r_idlh["severity"]["code"] == "above_idlh", r_idlh["severity"]
    r_pdk = assess_exceedance(cl, value=3, unit="мг/м³")
    assert r_pdk["comparison"]["pdk_ratio"] == 3.0 and r_pdk["severity"]["code"] == "above_pdk"
    print("\nOK: единицы не пересчитываются, severity только из корректного сравнения, honest-gap работает.")
