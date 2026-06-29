# -*- coding: utf-8 -*-
"""
ОПЕРАТИВНАЯ КАРТОЧКА ДИСПЕТЧЕРА ПРИ АВАРИИ с АХОВ.

Собирает в один экран то, что диспетчеру нужно в первые минуты: что за вещество, какая
зона заражения, что надеть, как оказать первую помощь, куда уводить людей и кого оповестить.

⚠️ СВЯТОЕ ПРАВИЛО (safety-critical). Этот модуль НИЧЕГО не выдумывает:
  • расстояния зоны — ТОЛЬКО из движка РД 52.04.253-90 (engine/rd_zone.py), без округления/упрощения;
  • СИЗ / первая помощь / IDLH / ООН-номер — ТОЛЬКО из существующих карточек (/emergency, паспорт,
    NIOSH IDLH, ERG-2024) с провенансом каждого значения;
  • телефоны ПАСФ/ЕДДС/диспетчера и имена — НЕ синтезируются: это ПЛЕЙСХОЛДЕРЫ «___»,
    которые заполняет предприятие;
  • поведение по плотности газа (тяжелее/легче воздуха) — ТОЛЬКО если есть подтверждённое
    физсвойство ρ_газа (из таблицы свойств РД 52.04.253-90); иначе «нет данных»;
  • это инструмент-подсказка по типовой методике; решение и ответственность — за человеком.

Изолированный новый код: переиспользует rd_zone.calc() (зоны) и при работе в сервисе —
результат эндпоинта /emergency (карточка). service.py НЕ редактируется.
"""
import os, json

try:
    import rd_zone  # тот же движок зон, что и эндпоинт /zone
except (FileNotFoundError, OSError, ImportError):
    rd_zone = None

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")

# Плотность воздуха при нормальных условиях, кг/м³ (справочная константа для сравнения, не норматив).
AIR_DENSITY_KGM3 = 1.293

# Чек-лист оповещения. ЗНАЧЕНИЯ ТЕЛЕФОНОВ НЕ ЗАДАЁМ — их заполняет предприятие (плейсхолдеры).
_NOTIFY_ROLES = [
    ("ЕДДС / единый номер экстренных служб", "вызов сил и средств, координация"),
    ("ПАСФ / газоспасательная служба", "локализация выброса, разведка зоны"),
    ("Диспетчер / руководитель смены предприятия", "оповещение, остановка процесса, ПЛАС"),
    ("Медицинская служба (скорая / здравпункт)", "приём поражённых, развёртывание помощи"),
    ("Оповещение персонала и населения в зоне", "эвакуация / укрытие по сигналу"),
    ("Надзорные органы (Ростехнадзор и др., по регламенту)", "уведомление об инциденте"),
]


def _load(fn, default):
    try:
        return json.load(open(os.path.join(_DATA, fn), encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return default


def _local_emergency(name):
    """Минимальная сборка аварийной карточки БЕЗ запуска сервиса — для standalone/__main__.

    В рабочем сервисе вместо этого передаётся готовый результат эндпоинта /emergency
    (параметр emergency=), чтобы переиспользовать его логику один в один.
    Возвращает подмножество полей в том же виде, что и service.emergency().
    """
    subs = _load("substances_clean.json", [])
    by_name = {s.get("name", "").lower(): s for s in subs} if isinstance(subs, list) else {}
    s = by_name.get((name or "").lower().strip())
    erg = _load("erg_ahov.json", {"cards": {}}).get("cards", {})
    ahov = _load("ahov_cards.json", {"cards": {}}).get("cards", {})
    idlh = _load("idlh.json", {})

    key = s["name"].lower() if s else (name or "").lower().strip()
    card = ahov.get(key)
    erec = erg.get(key)
    cas = (s or {}).get("cas")
    irec = idlh.get(cas) if cas else None
    irec = irec if (irec and irec.get("idlh") is not None) else None
    return {
        "substance": (s or {}).get("name") or name,
        "is_ahov": bool((card and card.get("ahov")) or erec),
        "un_number": (card or {}).get("un") or (erec or {}).get("un_number"),
        "adr_class": (card or {}).get("adr_class") or (erec or {}).get("adr_class"),
        "hazard_class": (s or {}).get("hazard_class"),
        "pdk_mgm3": (s or {}).get("pdk_mgm3"),
        "idlh": irec,
        "first_aid": (s or {}).get("first_aid"),
        "ppe": (s or {}).get("ppe"),
        "erg": erec,
        "guidance_source": "паспорт" if (s or {}).get("first_aid") else None,
    }


def _shelter_behavior(name):
    """Поведение укрытия/эвакуации по плотности газа.

    ТОЛЬКО при наличии подтверждённого ρ_газа из таблицы свойств РД 52.04.253-90.
    Иначе — честное «нет данных». Числа не выдумываем, поведение — следствие из плотности.
    """
    if rd_zone is None:
        return {"status": "нет данных",
                "reason": "движок РД 52.04.253-90 недоступен — плотность газа не подтверждена"}
    _, coef = rd_zone._alias_lookup(name)
    rho = (coef or {}).get("rho_gas")
    if not rho:
        return {"status": "нет данных",
                "reason": "нет подтверждённого значения плотности газа для вещества"}
    rho_kgm3 = rho * 1000.0   # rd_ahov хранит ρ в т/м³
    heavier = rho_kgm3 > AIR_DENSITY_KGM3
    return {
        "status": "ok",
        "rho_gas_kgm3": round(rho_kgm3, 3),
        "air_density_kgm3": AIR_DENSITY_KGM3,
        "heavier_than_air": heavier,
        "behavior": (
            "Газ ТЯЖЕЛЕЕ воздуха — стелется понизу, скапливается в подвалах, приямках, "
            "низинах, тоннелях. Укрытие — на ВЕРХНИХ этажах; уходить перпендикулярно ветру, "
            "по возможности вверх по рельефу. Низины и подземные сооружения опасны."
            if heavier else
            "Газ ЛЕГЧЕ воздуха — поднимается вверх, скапливается под перекрытиями и в верхних "
            "объёмах замкнутых помещений. Опасны верхние этажи и зоны под потолком; уходить "
            "перпендикулярно ветру. Проветривание — сверху."
        ),
        "source": (f"плотность газа ρ={round(rho_kgm3, 3)} кг/м³ из таблицы свойств АХОВ "
                   f"РД 52.04.253-90; сравнение с плотностью воздуха {AIR_DENSITY_KGM3} кг/м³"),
        "confidence": "needs_review",
    }


def _zone(name, mass_kg, weather):
    """Расчёт зоны через движок РД 52.04.253-90 как есть. Без массы — расчёт не делаем."""
    if rd_zone is None:
        return {"status": "недоступно", "reason": "движок РД 52.04.253-90 не загружен (нет rd_ahov.json)"}
    if not mass_kg or mass_kg <= 0:
        return {"status": "нужны исходные данные",
                "reason": "укажите массу выброса (кг) — без неё зона по методике не считается"}
    w = weather or {}
    q0_t = mass_kg / 1000.0   # методика работает в тоннах
    r = rd_zone.calc(
        name, q0_t,
        wind=w.get("wind_ms", 1.0),
        temp=w.get("temp_c", 20.0),
        stability=w.get("stability", "изотермия"),
        n_hours=w.get("n_hours", 1.0),
        spill=w.get("spill", "свободный"),
        dike_h=w.get("dike_h"),
    )
    if "error" in r:
        return {"status": "не рассчитано", "reason": r["error"],
                "available": r.get("available")}
    r["status"] = "ok"
    return r


def _notify_checklist():
    """Чек-лист оповещения как ПЛЕЙСХОЛДЕРЫ. Телефоны/имена НЕ выдумываем."""
    return {
        "filled_by": "предприятие",
        "note": "Телефоны и ответственные заполняются предприятием в карте оповещения / ПЛАС.",
        "items": [
            {"order": i + 1, "role": role, "purpose": why,
             "phone": "___", "responsible": "___", "placeholder": True}
            for i, (role, why) in enumerate(_NOTIFY_ROLES)
        ],
    }


def dispatch_card(substance, mass_kg=None, weather=None, emergency=None):
    """Собрать оперативную карточку диспетчера.

    substance — имя вещества (как в базе/синонимах);
    mass_kg   — масса выброса, кг (опц.; без неё зона не считается);
    weather   — dict: wind_ms, temp_c, stability, n_hours, spill, dike_h (опц.);
    emergency — готовый результат эндпоинта /emergency (опц.); если None — собираем локально.

    Детерминированно. Ничего не синтезирует сверх источников.
    """
    em = emergency if emergency is not None else _local_emergency(substance)
    name = em.get("substance") or substance

    ident = {
        "substance": name,
        "is_ahov": em.get("is_ahov"),
        "un_number": em.get("un_number"),
        "adr_class": em.get("adr_class"),
        "hazard_class": em.get("hazard_class"),
        "pdk_mgm3": em.get("pdk_mgm3"),
        "idlh": em.get("idlh"),          # порог NIOSH (когда без СИЗ опасно для жизни), needs_review
        "source": "ООН/ДОПОГ — аварийная карточка /emergency (ERG-2024 / перечень АХОВ); "
                  "ПДК/класс — паспорт вещества; IDLH — NIOSH (cdc.gov/niosh/idlh)",
    }

    actions = {
        "ppe": {"value": em.get("ppe"),
                "source": em.get("guidance_source") or "карточка /emergency",
                "present": bool(em.get("ppe"))},
        "first_aid": {"value": em.get("first_aid"),
                      "source": em.get("guidance_source") or "карточка /emergency",
                      "present": bool(em.get("first_aid"))},
        "idlh": em.get("idlh"),
        "note": "СИЗ и первая помощь — из карточки/паспорта с провенансом. "
                "Где значения нет — «нет данных», не додумывать.",
    }
    if not actions["ppe"]["present"]:
        actions["ppe"]["value"] = "нет данных — см. /emergency и паспорт вещества"
    if not actions["first_aid"]["present"]:
        actions["first_aid"]["value"] = "нет данных — см. /emergency и паспорт вещества"

    return {
        "substance": name,
        "tool_note": ("Инструмент-подсказка по типовой методике РД 52.04.253-90. "
                      "Не заменяет утверждённый расчёт объекта и ПЛАС. "
                      "Решение и ответственность — за человеком."),
        "method": "РД 52.04.253-90 (Методика прогнозирования масштабов заражения АХОВ)",
        "identification": ident,
        "zone": _zone(name, mass_kg, weather),
        "erg_distances": em.get("erg"),   # ориентир первого реагирования (ERG-2024), needs_review
        "actions": actions,
        "shelter_evacuation": _shelter_behavior(name),
        "notify": _notify_checklist(),
        "confidence": "needs_review",
    }


if __name__ == "__main__":
    # Самопроверка: детерминированный прогон на хлоре (тяжелее воздуха) и аммиаке (легче).
    for nm, mass in (("хлор", 1000), ("аммиак", 2000)):
        c = dispatch_card(nm, mass_kg=mass, weather={"wind_ms": 1.0, "temp_c": 20.0})
        z = c["zone"]; sh = c["shelter_evacuation"]; idn = c["identification"]
        print(f"\n=== {nm.upper()} — выброс {mass} кг ===")
        print("  ООН:", idn["un_number"], "| класс ДОПОГ:", idn["adr_class"],
              "| АХОВ:", idn["is_ahov"], "| IDLH:", (idn["idlh"] or {}).get("idlh"),
              (idn["idlh"] or {}).get("units"))
        if z.get("status") == "ok":
            print(f"  ЗОНА (РД 52.04.253-90): глубина {z['depth_total_km']} км "
                  f"(перв. {z['depth_primary_km']} / втор. {z['depth_secondary_km']} км); "
                  f"{z['method']}")
        else:
            print("  ЗОНА:", z.get("status"), "—", z.get("reason"))
        if sh.get("status") == "ok":
            print(f"  УКРЫТИЕ: {'тяжелее' if sh['heavier_than_air'] else 'легче'} воздуха "
                  f"(ρ={sh['rho_gas_kgm3']} кг/м³). {sh['behavior'][:70]}...")
        else:
            print("  УКРЫТИЕ:", sh.get("status"), "—", sh.get("reason"))
        print("  СИЗ есть:", c["actions"]["ppe"]["present"],
              "| первая помощь есть:", c["actions"]["first_aid"]["present"])
        print("  ОПОВЕЩЕНИЕ: телефоны-плейсхолдеры =",
              [it["phone"] for it in c["notify"]["items"]],
              "(", c["notify"]["filled_by"], ")")

    # Контроль святого правила: хлор тяжелее, аммиак легче, оба считают зону, телефоны пустые.
    cl = dispatch_card("хлор", mass_kg=1000)
    am = dispatch_card("аммиак", mass_kg=2000)
    assert cl["zone"]["status"] == "ok" and cl["zone"]["depth_total_km"] > 0
    assert am["zone"]["status"] == "ok" and am["zone"]["depth_total_km"] > 0
    assert cl["shelter_evacuation"]["heavier_than_air"] is True
    assert am["shelter_evacuation"]["heavier_than_air"] is False
    assert all(it["phone"] == "___" for it in cl["notify"]["items"])
    # Вещество без коэффициентов РД — зона не считается, ничего не выдумываем.
    unk = dispatch_card("диборан", mass_kg=500)
    assert unk["zone"]["status"] in ("не рассчитано", "нужны исходные данные")
    print("\nOK: самопроверка пройдена (зоны из методики, плотность из РД, телефоны-плейсхолдеры).")
