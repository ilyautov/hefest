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

# 6. Инвариант обезличивания: названия площадок живут в данных, не в рантайм-коде.
if [ -f data/plant_aliases.json ]; then
  leak=0
  python3 -c "
import json
d = json.load(open('data/plant_aliases.json', encoding='utf-8'))
print('\n'.join(sorted({v for v in d.get('aliases', {}).values() if len(v) > 5})))
" 2>/dev/null > /tmp/hefest_guard_names.txt || : > /tmp/hefest_guard_names.txt
  while IFS= read -r nm; do
    [ -z "$nm" ] && continue
    # shellcheck disable=SC2086
    if git grep -liF -e "$nm" -- $RUNTIME_PY >/dev/null 2>&1; then
      leak=1
      # shellcheck disable=SC2086
      git grep -liF -e "$nm" -- $RUNTIME_PY | sed "s/^/         «$nm» → /"
    fi
  done < /tmp/hefest_guard_names.txt
  rm -f /tmp/hefest_guard_names.txt
  [ "$leak" = 1 ] && bad "названий площадок нет в рантайм-коде" || ok "названий площадок нет в рантайм-коде"
else
  ok "названий площадок нет в рантайм-коде"
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
