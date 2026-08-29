# -*- coding: utf-8 -*-
"""
SDS-гигиена: аудит-лог запросов + состояние паспорта + дэшборд качества данных.

Из обзора SDS-софта (SafetyCulture/EHS Insight и др.) ключевые гигиенические функции —
аудит доступа, отслеживание полноты/актуальности паспортов. Реализуем БЕЗ фабрикации:
даты пересмотра не выдумываем, а показываем фактическое состояние данных
(source_tier, confidence, отсутствующие критичные поля).
"""
import os, json
from datetime import datetime, timezone
import baseline
import cas as cas_check

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
_LOG = os.path.join(_DATA, "audit_log.jsonl")

# Поля, без которых паспорт неполон для оперативного применения.
_CRITICAL = {"pdk_mgm3": "ПДК", "ppe": "СИЗ", "first_aid": "первая помощь",
             "hazard_class": "класс опасности", "storage": "хранение"}


# Ротация: чтобы аудит-лог не рос безгранично на проде. По умолчанию 50 МБ, держим 3 поколения.
_LOG_MAX = int(os.getenv("AUDIT_LOG_MAX_BYTES", str(50 * 1024 * 1024)))
_LOG_KEEP = int(os.getenv("AUDIT_LOG_KEEP", "3"))


def _rotate_if_big():
    try:
        if os.path.getsize(_LOG) < _LOG_MAX:
            return
    except OSError:
        return
    # audit_log.jsonl -> .1 -> .2 ... (старшее поколение удаляется)
    try:
        oldest = f"{_LOG}.{_LOG_KEEP}"
        if os.path.exists(oldest):
            os.remove(oldest)
        for i in range(_LOG_KEEP - 1, 0, -1):
            src = f"{_LOG}.{i}"
            if os.path.exists(src):
                os.replace(src, f"{_LOG}.{i+1}")
        os.replace(_LOG, f"{_LOG}.1")
    except OSError:
        pass


def audit(kind: str, query: str, extra: dict | None = None):
    """Дописать запись в аудит-лог (append-only jsonl). Не падает при ошибке записи."""
    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "kind": kind, "query": (query or "")[:300]}
    if extra:
        rec.update({k: v for k, v in extra.items() if v is not None})
    try:
        _rotate_if_big()
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return rec


def audit_tail(n: int = 50) -> list:
    """Последние n записей аудит-лога (новые сверху)."""
    if not os.path.exists(_LOG):
        return []
    try:
        with open(_LOG, encoding="utf-8") as f:
            lines = f.readlines()[-n:]
        return [json.loads(x) for x in reversed(lines) if x.strip()]
    except OSError:
        return []


def passport_state(sub: dict) -> dict:
    """Состояние конкретного паспорта: полнота + верификация. Без выдуманных дат."""
    missing = [label for k, label in _CRITICAL.items()
               if not sub.get(k) and sub.get(k) != 0]
    conf = sub.get("confidence")
    tier = sub.get("source_tier")
    if conf == "needs_review":
        state, hint = "needs_review", "Данные требуют сверки с первоисточником."
    elif missing:
        state, hint = "incomplete", "Не хватает критичных полей: " + ", ".join(missing) + "."
    else:
        state, hint = "ok", "Критичные поля заполнены."
    # Контрольная цифра CAS проверяется на лету: неверный номер — повод для сверки, а не
    # для автоисправления (подбор «похожего верного» номера = выдуманный идентификатор).
    cas_status = cas_check.check(sub.get("cas"))
    if not cas_status["ok"] and cas_status["status"] != cas_check.СТАТУС_ПУСТО:
        hint = (hint + " " + cas_status["note"]).strip()
    return {"name": sub.get("name"), "state": state, "missing": missing,
            "source_tier": tier, "confidence": conf, "hint": hint,
            "cas_check": cas_status,
            "data_grade": baseline.data_grade(sub)}


def quality_dashboard(subs: list) -> dict:
    """Агрегат качества базы: верификация, тиры, дыры в критичных полях."""
    n = len(subs)
    by_conf, by_tier, by_grade = {}, {}, {"passport": 0, "partial": 0, "baseline": 0}
    field_gaps = {label: 0 for label in _CRITICAL.values()}
    complete = needs_review = 0
    for s in subs:
        c = s.get("confidence") or "—"; t = s.get("source_tier") or "—"
        by_conf[c] = by_conf.get(c, 0) + 1
        by_tier[t] = by_tier.get(t, 0) + 1
        by_grade[baseline.data_grade(s)] += 1
        if c == "needs_review":
            needs_review += 1
        gaps = [label for k, label in _CRITICAL.items() if not s.get(k) and s.get(k) != 0]
        for g in gaps:
            field_gaps[g] += 1
        if not gaps and c != "needs_review":
            complete += 1
    cas_audit = cas_check.audit(subs)
    return {
        "substances": n,
        "complete": complete, "complete_pct": round(100 * complete / n, 1) if n else 0,
        "needs_review": needs_review,
        "data_grade": by_grade,
        "by_confidence": dict(sorted(by_conf.items(), key=lambda x: -x[1])),
        "by_source_tier": dict(sorted(by_tier.items())),
        "field_gaps": field_gaps,
        "cas_integrity": {
            "checked": cas_audit["checked"],
            "by_status": cas_audit["by_status"],
            "suspect_in_verified_core": [z for z in cas_audit["suspect"]
                                         if z.get("confidence") != "needs_review"],
            "suspect_total": len(cas_audit["suspect"]),
            "note": cas_audit["note"],
        },
        "note": "Гигиена данных: полнота критичных полей + статус верификации. data_grade: "
                "passport (паспортные СИЗ+ПП+хранение) / partial / baseline (типовое по группе). "
                "Даты пересмотра не синтезируются; типовое руководство НЕ маскируется под паспортное.",
    }
