# -*- coding: utf-8 -*-
"""
Слой ЭКСПЕРТНОЙ ВЕРИФИКАЦИИ — отдельный от алгоритмической `confidence`.

`confidence` отвечает на вопрос «насколько уверена МАШИНА в значении» (выведено из источника/группы).
`verification` отвечает на вопрос «подтвердил ли ЧЕЛОВЕК (инженер ОТ/ПБ, эколог) это значение для прода».
Это РАЗНЫЕ вещи: значение может быть confidence=high (эталонный источник), но всё ещё НЕ подписанным
ответственным лицом конкретного предприятия — а для безопасно-критичного прода нужна именно подпись.

ПРИНЦИП: по умолчанию ВСЁ — needs_review. Статус `verified` ставит ТОЛЬКО реальный человек через /verify
(пишем кто и когда). Система сама ничего «verified» не помечает — иначе это была бы выдумка доверия.

Файл: data/verification.json = { name_lower: {status, by, role, at, note, fields:[...]} , _meta:{} }
Статусы: needs_review (дефолт) | verified (подписано экспертом) | rejected (эксперт нашёл ошибку).
"""
import os, json, datetime

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
_FILE = os.path.join(_DATA, "verification.json")

# Кэш в памяти + ленивая перезагрузка по mtime (несколько воркеров uvicorn увидят чужие подписи).
_cache = {"mtime": None, "data": None}

_DEFAULT_META = {
    "scheme": "expert-signoff v1",
    "disclaimer": "Статус verified означает: значение подтверждено named-экспертом предприятия (ОТ/ПБ или "
                  "эколог) на дату подписи. needs_review — машинные данные, для прода требуют проверки. "
                  "Первоисточник во всех случаях — действующий паспорт безопасности (ГОСТ 30333).",
    "statuses": {"needs_review": "по умолчанию: машинные данные, не подписаны",
                 "verified": "подтверждено экспертом (кто/когда зафиксированы)",
                 "rejected": "эксперт нашёл ошибку — НЕ показывать как факт"},
}


def _load():
    try:
        mt = os.path.getmtime(_FILE)
    except OSError:
        mt = None
    if _cache["mtime"] != mt or _cache["data"] is None:
        try:
            _cache["data"] = json.load(open(_FILE, encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            _cache["data"] = {"_meta": _DEFAULT_META}
        _cache["mtime"] = mt
    return _cache["data"]


def _save(data):
    data["_meta"] = {**_DEFAULT_META, **data.get("_meta", {})}
    tmp = _FILE + ".tmp"
    json.dump(data, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, _FILE)  # атомарно: воркеры не прочитают полу-записанный файл
    _cache["mtime"] = None  # форс-перечитать


def status_for(name):
    """Статус верификации вещества по имени. Дефолт — needs_review (ничего не подписано)."""
    if not name:
        return {"status": "needs_review", "signed": False}
    rec = _load().get((name or "").lower().strip())
    if not rec:
        return {"status": "needs_review", "signed": False}
    return {"status": rec.get("status", "needs_review"),
            "signed": rec.get("status") == "verified",
            "by": rec.get("by"), "role": rec.get("role"),
            "at": rec.get("at"), "note": rec.get("note"),
            "fields": rec.get("fields")}


def mark(name, status, by, role=None, note=None, fields=None, now=None):
    """Поставить подпись эксперта. by обязателен (кто отвечает). Пишем дату.
    Возвращает (ok, message-или-record)."""
    key = (name or "").lower().strip()
    if not key:
        return False, "пустое имя вещества"
    if status not in ("needs_review", "verified", "rejected"):
        return False, "статус: needs_review | verified | rejected"
    if status in ("verified", "rejected") and not (by or "").strip():
        return False, "для verified/rejected обязательно поле 'by' (ФИО/должность ответственного)"
    data = _load()
    rec = {"status": status, "by": by, "role": role, "note": note, "fields": fields,
           "at": (now or datetime.datetime.now()).isoformat(timespec="seconds")}
    rec = {k: v for k, v in rec.items() if v is not None}
    data[key] = rec
    _save(data)
    return True, rec


def records(status=None):
    """Список явных записей (подписи/отклонения) для дашборда: [{name, status, by, role, at}]."""
    d = _load()
    out = []
    for k, v in d.items():
        if k == "_meta":
            continue
        if status and v.get("status") != status:
            continue
        out.append({"name": k, "status": v.get("status"), "by": v.get("by"),
                    "role": v.get("role"), "at": v.get("at"), "fields": v.get("fields")})
    out.sort(key=lambda r: r.get("at") or "", reverse=True)
    return out


def summary(total_substances=None):
    """Счётчики статусов по всей базе — для дашборда готовности."""
    d = _load()
    recs = {k: v for k, v in d.items() if k != "_meta"}
    verified = sum(1 for v in recs.values() if v.get("status") == "verified")
    rejected = sum(1 for v in recs.values() if v.get("status") == "rejected")
    out = {"verified": verified, "rejected": rejected, "explicit_records": len(recs)}
    if total_substances is not None:
        out["total"] = total_substances
        out["needs_review"] = total_substances - verified - rejected
        out["verified_pct"] = round(100 * verified / total_substances, 1) if total_substances else 0
    return out
