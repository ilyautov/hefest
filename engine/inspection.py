# -*- coding: utf-8 -*-
"""
РЕЖИМ ИНСПЕКТОРА — химическая готовность площадки К ПРОВЕРКЕ (data-derived).

⚠️ СВЯТОЕ ПРАВИЛО. Мы НЕ воспроизводим официальный проверочный лист Ростехнадзора/
Роспотребнадзора и НЕ цитируем номера пунктов и формулировки требований надзора (их выдумывать
нельзя). Вместо этого дашборд показывает ИЗМЕРИМУЮ химическую готовность, ВЫВЕДЕННУЮ ИЗ ДАННЫХ,
которые у системы УЖЕ есть с провенансом: покрытие ПДК, маркировки СГС, класса опасности,
экспертной верификации, совместимости хранения, актуальности нормативной базы и критичных
разделов ГОСТ 30333. Каждый пункт — это НАША внутренняя метрика покрытия данных, а не пункт
надзорного листа. Где метрика неполна — честно «N веществ требуют проверки», ничего не додумываем.

Сверку этих метрик с актуальным проверочным листом надзора выполняет ответственный специалист.

Переиспользует (единый код = единый результат с карточками веществ):
  * verification.status_for — подпись эксперта (verified / needs_review / rejected);
  * normative.by_id / REGISTER — статус актов (current / superseded / historic);
  * gost_sections.coverage_for — покрытие 16 разделов ГОСТ 30333 для вещества;
  * registry.conflicts — опасные пары для совместного хранения;
  * baseline.data_grade / ghs_map.ghs_profile — полнота данных и определимость маркировки.

Детерминированно (никакого LLM): одни и те же данные → один и тот же отчёт. Самопроверка в __main__.
"""
import os
import baseline, gost_sections, normative, registry, verification, ghs_map

# Разделы ГОСТ 30333, критичные для «химической готовности к работе с веществом».
# 2 — идентификация опасности; 4 — первая помощь; 7 — хранение/совместимость; 8 — контроль (ПДК)+СИЗ.
_CRITICAL_SECTIONS = {2, 4, 7, 8}
_GOOD = ("full", "partial")  # «закрыто структурно» = есть наши данные (а не честный пробел/корпус)


def _status(covered, total):
    """ok — закрыто полностью; partial — частично; gap — данных нет."""
    if total <= 0:
        return "gap"
    if covered >= total:
        return "ok"
    return "partial" if covered > 0 else "gap"


def _gap_note(covered, total, unit="вещество", units=("вещества", "веществ")):
    """Честная формулировка пробела: «N веществ требуют проверки» (а не маскировка)."""
    miss = max(total - covered, 0)
    if miss == 0:
        return None
    # грубая, но достаточная русская плюрализация для счётчика
    if miss % 10 == 1 and miss % 100 != 11:
        word = unit
    elif miss % 10 in (2, 3, 4) and miss % 100 not in (12, 13, 14):
        word = units[0]
    else:
        word = units[1]
    return f"{miss} {word} требуют проверки"


def _audit_outdated_refs():
    """Системный (НЕ по площадке) счётчик устаревших ссылок на НПА из предрасчёта аудита.
    Читаем готовый data/version_audit.json, чтобы не сканировать репозиторий на каждый запрос."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "version_audit.json")
    try:
        import json
        rep = json.load(open(path, encoding="utf-8"))
        return rep.get("outdated_refs")
    except Exception:
        return None


def _resolved_subs(plant_obj, subs_by_name):
    """Реальные карточки веществ площадки (только распознанные в базе)."""
    out = []
    for name in plant_obj.get("matched_substances", []):
        s = subs_by_name.get(name.lower())
        if s:
            out.append(s)
    return out


def plant_readiness(plant_obj, subs_by_name, assemble=None):
    """
    Агрегирует РЕАЛЬНЫЕ метрики химической готовности площадки по её веществам.

    plant_obj    — запись завода из plants_linked (matched_substances и т.д.).
    subs_by_name — {name_lower: substance_dict} (как SUBS в сервисе).
    assemble     — callable(s)->dict для полной сборки карточки (service._assemble), чтобы покрытие
                   ГОСТ совпадало с /substance. Без него используется честный минимум (baseline).

    Возвращает {plant, substances_total, progress_pct, metrics:[...], disclaimer, ...}.
    Каждая метрика: {key,label,covered,total,status: ok|partial|gap,note}.
    """
    if assemble is None:
        assemble = lambda s: {**s, "guidance": baseline.baseline_for(s)}

    subs = _resolved_subs(plant_obj, subs_by_name)
    n = len(subs)
    metrics = []

    # 1) ПДК рабочей зоны (раздел 8) — есть ли гигиенический норматив для вещества.
    pdk = sum(1 for s in subs if s.get("pdk_mgm3") not in (None, ""))
    metrics.append({
        "key": "pdk", "label": "ПДК рабочей зоны (раздел 8, СанПиН 1.2.3685-21)",
        "covered": pdk, "total": n, "status": _status(pdk, n),
        "note": _gap_note(pdk, n) or "ПДК заданы для всех веществ площадки",
    })

    # 2) Класс опасности (ГОСТ 12.1.007-76).
    hc = sum(1 for s in subs if s.get("hazard_class") not in (None, ""))
    metrics.append({
        "key": "hazard_class", "label": "Класс опасности (ГОСТ 12.1.007-76)",
        "covered": hc, "total": n, "status": _status(hc, n),
        "note": _gap_note(hc, n) or "класс опасности определён для всех веществ",
    })

    # 3) Маркировка СГС/GHS (раздел 2) — определимы ли пиктограммы; честно считаем «выведенные по классу».
    ghs_cov = derived = 0
    for s in subs:
        prof = ghs_map.ghs_profile(s)
        if prof.get("pictograms"):
            ghs_cov += 1
            if prof.get("confidence") != "from_labels":
                derived += 1
    note = _gap_note(ghs_cov, n)
    if derived:
        d = f"из них {derived} выведены по классу опасности (не из меток паспорта) — сверить"
        note = (note + "; " + d) if note else d
    metrics.append({
        "key": "ghs", "label": "Предупредительная маркировка СГС (раздел 2, ГОСТ 31340-2013)",
        "covered": ghs_cov, "total": n, "status": _status(ghs_cov, n),
        "note": note or "маркировка определима для всех веществ",
    })

    # 4) Экспертная верификация — подписано ли значение ответственным лицом (verified vs needs_review).
    verified = rejected = 0
    for s in subs:
        st = verification.status_for(s["name"]).get("status")
        if st == "verified":
            verified += 1
        elif st == "rejected":
            rejected += 1
    need = n - verified - rejected
    vnote_parts = []
    if need:
        vnote_parts.append(f"{need} требуют проверки (подпись ставит инженер ОТ/ПБ)")
    if rejected:
        vnote_parts.append(f"{rejected} отклонены экспертом (есть ошибка)")
    metrics.append({
        "key": "verification", "label": "Экспертная верификация (подпись ответственного лица)",
        "covered": verified, "total": n, "status": _status(verified, n),
        "note": "; ".join(vnote_parts) or "все значения подтверждены экспертом",
    })

    # 5) Совместимость хранения (раздел 7) — опасные пары для совместного хранения (registry.conflicts).
    conf = registry.conflicts(plant_obj, subs_by_name)
    forbidden = sum(1 for c in conf if c["verdict"] == "forbidden")
    caution = sum(1 for c in conf if c["verdict"] == "caution")
    total_pairs = n * (n - 1) // 2
    safe_pairs = total_pairs - forbidden - caution
    if forbidden:
        st_store = "gap"
    elif caution:
        st_store = "partial"
    else:
        st_store = "ok"
    snote = []
    if forbidden:
        snote.append(f"{forbidden} запрещённых пар — развести по разным помещениям")
    if caution:
        snote.append(f"{caution} пар требуют осторожности")
    metrics.append({
        "key": "storage_compat", "label": "Совместимость хранения (раздел 7, безопасные пары)",
        "covered": safe_pairs, "total": total_pairs, "status": st_store,
        "note": "; ".join(snote) or ("опасных пар не найдено" if total_pairs else "одно вещество — пар нет"),
    })

    # 6) Актуальность нормативной базы — все ли акты, на которые опираются данные, в действующей редакции.
    ref_ids = set()
    for s in subs:
        ref_ids.add("ГОСТ 30333-2022")
        if s.get("hazard_class") not in (None, ""):
            ref_ids.add("ГОСТ 12.1.007-76")
        if s.get("pdk_mgm3") not in (None, ""):
            ref_ids.add("ГОСТ 12.1.005-88"); ref_ids.add("СанПиН 1.2.3685-21")
        if s.get("ghs"):
            ref_ids.add("ГОСТ 31340-2013")
    current = superseded = 0
    stale_acts = []
    for aid in ref_ids:
        a = normative.by_id(aid)
        if a and a.get("status") == "current":
            current += 1
        elif a and a.get("status") == "superseded":
            superseded += 1
            stale_acts.append(aid)
    total_acts = len(ref_ids)
    nnote = []
    if superseded:
        nnote.append("устаревшие редакции: " + ", ".join(sorted(stale_acts)))
    sys_outdated = _audit_outdated_refs()
    if sys_outdated:
        nnote.append(f"по системе в целом аудит нашёл {sys_outdated} устаревших упоминаний в коде/доках "
                     f"(технический долг, не влияет на значения площадки)")
    metrics.append({
        "key": "normative", "label": "Актуальность нормативной базы (ссылки на действующие редакции НПА)",
        "covered": current, "total": total_acts, "status": _status(current, total_acts),
        "note": "; ".join(nnote) or "все источники нормативки — в действующей редакции",
    })

    # 7) Покрытие критичных разделов ГОСТ 30333 (2,4,7,8) по веществам площадки.
    crit_cells = covered_cells = 0
    for s in subs:
        cov = gost_sections.coverage_for(assemble(s))
        for sec in cov["sections"]:
            if sec["n"] in _CRITICAL_SECTIONS:
                crit_cells += 1
                if sec["status"] in _GOOD:
                    covered_cells += 1
    metrics.append({
        "key": "gost_critical", "label": "Критичные разделы ГОСТ 30333 (опасность, 1-я помощь, хранение, ПДК/СИЗ)",
        "covered": covered_cells, "total": crit_cells, "status": _status(covered_cells, crit_cells),
        "note": _gap_note(covered_cells, crit_cells, "ячейка раздел×вещество",
                          ("ячейки", "ячеек")) or "критичные разделы закрыты структурно по всем веществам",
    })

    # Общий процент — среднее по покрытию метрик (метрики без знаменателя не учитываем).
    ratios = [m["covered"] / m["total"] for m in metrics if m["total"] > 0]
    progress_pct = round(100 * sum(ratios) / len(ratios), 1) if ratios else 0.0

    return {
        "plant": plant_obj.get("plant"),
        "inn": plant_obj.get("inn"),
        "substances_total": n,
        "unmatched": plant_obj.get("unmatched_substances") or [],
        "progress_pct": progress_pct,
        "metrics": metrics,
        "basis": "Метрики выведены из данных системы с провенансом (слои ПДК/СГС/верификации/"
                 "совместимости/нормативки/ГОСТ-покрытия). Это НЕ официальный проверочный лист надзора.",
        "disclaimer": "Химическая готовность ПО ДАННЫМ СИСТЕМЫ. Это не воспроизведение проверочного "
                      "листа Ростехнадзора/Роспотребнадзора и не цитата требований надзора. Сверку с "
                      "актуальным проверочным листом надзора выполняет ответственный специалист предприятия.",
    }


def resolve_plant(name, plants, plant_triggers):
    """Резолв площадки по части имени (как /plant в сервисе): возвращает plant_obj или None."""
    ql = (name or "").lower()
    for trig, key in plant_triggers.items():
        if trig in ql and key in plants:
            return plants[key]
    # запасной путь: прямое совпадение по ключу/имени
    if ql in plants:
        return plants[ql]
    for p in plants.values():
        if ql and ql in p.get("plant", "").lower():
            return p
    return None


if __name__ == "__main__":  # самопроверка на одной площадке (детерминированно)
    import json
    here = os.path.dirname(os.path.abspath(__file__))
    data = os.path.join(here, "..", "data")
    subs_list = json.load(open(os.path.join(data, os.getenv("SUBS_FILE", "substances_clean.json")), encoding="utf-8"))
    subs_by_name = {s["name"].lower(): s for s in subs_list}
    plants = {p["plant"].lower(): p for p in json.load(open(os.path.join(data, "plants_linked.json"), encoding="utf-8"))["plants"]}

    plant_obj = next(iter(plants.values()))  # первая площадка
    rep = plant_readiness(plant_obj, subs_by_name)

    print(f"=== РЕЖИМ ИНСПЕКТОРА — самопроверка ===")
    print(f"Площадка: {rep['plant']} (ИНН {rep['inn']}), веществ: {rep['substances_total']}")
    print(f"Общая химическая готовность ПО ДАННЫМ: {rep['progress_pct']}%\n")
    for m in rep["metrics"]:
        mark = {"ok": "OK ", "partial": "~~ ", "gap": "!! "}[m["status"]]
        print(f"  {mark}{m['label']}")
        print(f"        {m['covered']}/{m['total']}  — {m['note']}")
    print(f"\nДисклеймер: {rep['disclaimer']}")

    # Инварианты самопроверки.
    assert rep["metrics"], "метрики не пустые"
    assert all(m["status"] in ("ok", "partial", "gap") for m in rep["metrics"]), "статус из множества ok/partial/gap"
    assert all(m["covered"] <= m["total"] for m in rep["metrics"]), "covered не превышает total"
    assert 0 <= rep["progress_pct"] <= 100, "процент в диапазоне 0..100"
    # детерминизм: повторный прогон даёт тот же результат
    assert plant_readiness(plant_obj, subs_by_name) == rep, "детерминированность"
    print("\n[OK] инварианты пройдены, результат детерминирован.")
