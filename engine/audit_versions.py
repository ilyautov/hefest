# -*- coding: utf-8 -*-
"""
Аудит актуальности ссылок на нормативку. Сканирует код/данные/доки, сверяет встреченные
ссылки на ГОСТ/ГН/СанПиН/РД/ФЗ с реестром normative.REGISTER и помечает устаревшие редакции.

Запуск (build-time):  python3 engine/audit_versions.py
Результат:            печать отчёта + data/version_audit.json (читается дашбордом /gost и доками).

СВЯТОЕ ПРАВИЛО: ничего не «исправляет» сам и не выдумывает — только находит и сообщает,
ссылаясь на реестр. Решение об обновлении формулировок — за человеком.
"""
import os, re, json, sys

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import normative  # noqa: E402

SCAN_DIRS = ["engine", "docs", "data"]
SCAN_ROOT_FILES = ["README.md", "WORKLOG.md"]
SKIP_FILES = {"version_audit.json", "audit_versions.py", "normative.py"}
EXTS = (".py", ".html", ".md", ".json")

# Какой акт «устарел» и чем заменён — из реестра.
SUPERSEDED = [a for a in normative.REGISTER if a["status"] in ("superseded",)]
VERIFY = [a for a in normative.REGISTER if a["status"] in ("verify", "historic")]


def _iter_files():
    for d in SCAN_DIRS:
        p = os.path.join(ROOT, d)
        if not os.path.isdir(p):
            continue
        for root, _, files in os.walk(p):
            for f in files:
                if f in SKIP_FILES or not f.endswith(EXTS) or ".bak." in f:
                    continue
                yield os.path.join(root, f)
    for f in SCAN_ROOT_FILES:
        p = os.path.join(ROOT, f)
        if os.path.isfile(p):
            yield p


def audit():
    findings = []   # {act, replaced_by, file, line, text}
    verify_hits = {}  # act_id -> count
    for path in _iter_files():
        rel = os.path.relpath(path, ROOT)
        try:
            lines = open(path, encoding="utf-8").read().splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines, 1):
            for act in SUPERSEDED:
                for pat in act["patterns"]:
                    if pat in line:
                        findings.append({
                            "act": act["id"], "replaced_by": act.get("replaced_by") or act.get("id"),
                            "file": rel, "line": i, "text": line.strip()[:160],
                        })
            for act in VERIFY:
                for pat in act["patterns"]:
                    if pat in line:
                        verify_hits[act["id"]] = verify_hits.get(act["id"], 0) + 1

    by_file = {}
    for f in findings:
        by_file.setdefault(f["file"], 0)
        by_file[f["file"]] += 1

    report = {
        "outdated_refs": len(findings),
        "files_affected": len(by_file),
        "findings": findings,
        "by_file": by_file,
        "verify_acts": [{"id": k, "mentions": v, "note": (normative.by_id(k) or {}).get("note")}
                        for k, v in sorted(verify_hits.items())],
        "register_summary": normative.summary_counts(),
        "note": "Устаревшие ссылки на нормативку. Обновить формулировку или явно пометить как "
                "историческую редакцию. verify_acts — статус/редакцию подтвердить по первоисточнику.",
    }
    return report


def main():
    rep = audit()
    out = os.path.join(ROOT, "data", "version_audit.json")
    json.dump(rep, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"=== Аудит версий нормативки ===")
    print(f"Устаревших ссылок: {rep['outdated_refs']}  в файлах: {rep['files_affected']}")
    print(f"Распределение реестра по статусу: {rep['register_summary']['by_status']}")
    print()
    if rep["findings"]:
        print("Устаревшие ссылки (акт -> заменён на | файл:строка):")
        for f in rep["findings"][:40]:
            print(f"  {f['act']:22} -> {f['replaced_by']:18} | {f['file']}:{f['line']}")
        if len(rep["findings"]) > 40:
            print(f"  … ещё {len(rep['findings'])-40}")
    print()
    if rep["verify_acts"]:
        print("Требуют подтверждения редакции/статуса:")
        for v in rep["verify_acts"]:
            print(f"  {v['id']:22} (упоминаний: {v['mentions']})")
    print(f"\nОтчёт сохранён: {os.path.relpath(out, ROOT)}")


if __name__ == "__main__":
    main()
