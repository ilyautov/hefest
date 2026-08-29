#!/bin/sh
# guard.sh — предпубликационный сторож.
#
# Блокирует push, если в трекаемых файлах оказалось то, что не должно уехать в публичный
# репозиторий: секреты, .env, рантайм-состояние, данные предприятия, реальные названия
# площадок в рантайм-коде, а также обязательные файлы публичного репозитория на месте.
#
# Ритуал: перед каждым push к публикации — `make guard`.
# Как git-хук:  ln -s ../../scripts/guard.sh .git/hooks/pre-push
#
# Скрипт исключает себя из скана: иначе его собственные паттерны дадут ложное срабатывание.
set -e
self='scripts/guard.sh'
fail=0

# Файлы крупнее порога допустимы вне Git LFS только по явному списку.
# data/corpus_full_clean.json — рабочий корпус: без него сервис не поднимается у того, кто
# просто склонировал репозиторий, а класть его в LFS значит сломать сценарий «клон без LFS».
LFS_EXEMPT='data/corpus_full_clean.json'
MAX_BYTES=20971520   # 20 МБ

# Эталонные наборы запросов (evaluate.py, eval_*.py) по своей природе привязаны к конкретному
# реестру площадок: у них руками выписаны ожидаемые вещества. Из проверки исключены осознанно.
RUNTIME_PY="engine/*.py :!engine/evaluate.py :!engine/eval_*.py"

report() { printf '  %s %s\n' "$1" "$2"; }
ok()     { report 'ok    ' "$1"; }
bad()    { report 'ПРОВАЛ' "$1"; fail=1; }

echo "guard: предпубликационная проверка"

# 1. Секреты: паттерн ловит РЕАЛЬНЫЙ ключ (префикс + хвост), а не упоминание префикса в доке.
if git grep -lE 'sk-ant-[A-Za-z0-9-]{20,}|sk-or-v1-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|BEGIN (RSA|OPENSSH|DSA|EC) PRIVATE KEY' -- . ":!$self" >/dev/null 2>&1; then
  bad "секреты в трекаемых файлах"
  git grep -lE 'sk-ant-[A-Za-z0-9-]{20,}|sk-or-v1-|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}' -- . ":!$self" | sed 's/^/         /'
else
  ok "секреты в трекаемых файлах"
fi

# 2. .env в любом виде и на любой глубине; шаблоны — задокументированное исключение.
env_leak=$(git ls-files | grep -iE '(^|/)\.env' | grep -vE '(^|/)\.env\.(example|sample|template)$' || true)
if [ -n "$env_leak" ]; then
  bad ".env вне шаблонов не трекается"; echo "$env_leak" | sed 's/^/         /'
else
  ok ".env вне шаблонов не трекается"
fi

# 3. Рантайм-состояние и локальные артефакты: аудит-лог запросов, снимки, настройки агентов.
state_leak=$(git ls-files | grep -E '^(data/audit_log\.jsonl|screenshots/|\.playwright-mcp/|\.claude/|\.codex/)' || true)
if [ -n "$state_leak" ]; then
  bad "рантайм-состояние не трекается"; echo "$state_leak" | sed 's/^/         /'
else
  ok "рантайм-состояние не трекается"
fi

# 4. Данные предприятия: реальные паспорта и выгрузки конкретного завода не публикуются.
plant_leak=$(git ls-files | grep -iE '(^|/)(sds_real|real_passports|plant_data|заводские|выгрузка)' || true)
if [ -n "$plant_leak" ]; then
  bad "данные предприятия не трекаются"; echo "$plant_leak" | sed 's/^/         /'
else
  ok "данные предприятия не трекаются"
fi

# 5. Крупные файлы: либо Git LFS, либо явное исключение выше.
big=$(git ls-files | while read -r f; do
  [ -f "$f" ] || continue
  if echo " $LFS_EXEMPT " | grep -qF " $f "; then continue; fi
  size=$(wc -c < "$f" 2>/dev/null || echo 0)
  if [ "$size" -gt "$MAX_BYTES" ]; then
    git check-attr filter -- "$f" 2>/dev/null | grep -q 'filter: lfs' || echo "$f ($((size/1048576)) МБ)"
  fi
done)
if [ -n "$big" ]; then
  bad "крупные файлы только через Git LFS"; echo "$big" | sed 's/^/         /'
else
  ok "крупные файлы только через Git LFS"
fi

# 6. Главный инвариант публикации: сведений о ЮРИДИЧЕСКИХ ЛИЦАХ в репозитории нет.
#    Ни реестра площадок, ни ИНН, ни названий организаций — ни в данных, ни в коде, ни в
#    примерах интерфейса, ни в наборах для eval (см. DATA-LICENSE.md, раздел 4).

# 6а. Реестр площадок и производные от него файлы не трекаются.
registry_leak=$(git ls-files | grep -E '^data/(plants(_linked)?(_demo)?\.json|plant_aliases\.json|plants_local.*\.json)$' || true)
if [ -n "$registry_leak" ]; then
  bad "реестр площадок не трекается"; echo "$registry_leak" | sed 's/^/         /'
else
  ok "реестр площадок не трекается"
fi

# 6б. ИНН: поле в данных или голая последовательность из 10/12 цифр рядом со словом ИНН.
inn_leak=$(git grep -lE '"inn"[[:space:]]*:[[:space:]]*"[0-9]{10,12}"|ИНН[[:space:]]*:?[[:space:]]*[0-9]{10,12}' -- . ":!$self" || true)
if [ -n "$inn_leak" ]; then
  bad "ИНН в трекаемых файлах"; echo "$inn_leak" | sed 's/^/         /'
else
  ok "ИНН в трекаемых файлах"
fi

# 6в. Названия организаций. Денайлист хранится ВНЕ репозитория (.private/ в .gitignore),
#     чтобы сам сторож не носил в публичном коде список реальных компаний. Нет файла —
#     проверка пропускается: она защищает владельца, а не форкнувшего.
if [ -f .private/entities-denylist.txt ]; then
  entity_leak=0
  while IFS= read -r nm; do
    case "$nm" in ''|'#'*) continue ;; esac
    if git grep -liF -e "$nm" -- . ":!$self" >/dev/null 2>&1; then
      entity_leak=1
      git grep -liF -e "$nm" -- . ":!$self" | sed 's/^/         название организации в: /' 
    fi
  done < .private/entities-denylist.txt
  [ "$entity_leak" = 1 ] && bad "названий организаций нет в трекаемых файлах" \
                         || ok "названий организаций нет в трекаемых файлах"
else
  ok "названий организаций нет (денайлист не задан — проверка пропущена)"
fi

# 6г. Денайлист не должен отставать от реестра: добавили площадку — сторож обязан о ней
#     знать, иначе проверка 6в молча пропустит новое название. Список производный, а не
#     рукописный (scripts/sync_denylist.py). Без реестра шаг пропускается.
if [ -f data/plants.json ] && [ -f scripts/sync_denylist.py ]; then
  if "${PY:-python3}" scripts/sync_denylist.py --check >/dev/null 2>&1; then
    ok "денайлист покрывает реестр площадок"
  else
    bad "денайлист покрывает реестр площадок"
    "${PY:-python3}" scripts/sync_denylist.py --check 2>&1 | sed 's/^/        /'
  fi
fi

# 7. Обязательные файлы публичного репозитория.
missing=""
for f in LICENSE DATA-LICENSE.md DISCLAIMER.md LIMITATIONS.md SECURITY.md CONTRIBUTING.md \
         CODE_OF_CONDUCT.md GOVERNANCE.md SUPPORT.md README.md; do
  [ -f "$f" ] || missing="$missing $f"
done
if [ -n "$missing" ]; then
  bad "файлы публичного репозитория на месте"; echo "        нет:$missing"
else
  ok "файлы публичного репозитория на месте"
fi

if [ "$fail" = 0 ]; then
  echo "guard: OK — публиковать можно"
else
  echo "guard: ПРОВАЛ — push заблокирован"
  exit 1
fi
