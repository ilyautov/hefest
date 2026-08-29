"""Готовность репозитория к публичной публикации.

Тесты этого файла защищают не поведение программы, а обещания, которые репозиторий даёт
постороннему человеку: лицензия на месте, границы применения названы, числа в README не
разошлись с данными, секреты не утекли. Всё, что здесь проверяется, ломается тихо и
обнаруживается поздно — поэтому проверяется автоматически.
"""
import io
import json
import os
import re
import subprocess

import pytest

from conftest import DATA

КОРЕНЬ = os.path.abspath(os.path.join(DATA, ".."))

ОБЯЗАТЕЛЬНЫЕ_ФАЙЛЫ = [
    "LICENSE", "DATA-LICENSE.md", "DISCLAIMER.md", "LIMITATIONS.md",
    "SECURITY.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "GOVERNANCE.md",
    "SUPPORT.md", "README.md", "Makefile", "scripts/guard.sh",
    ".github/PULL_REQUEST_TEMPLATE.md", ".github/workflows/ci.yml",
    ".github/ISSUE_TEMPLATE/normative-dispute.yml",
]


def _прочитать(относительный_путь):
    with io.open(os.path.join(КОРЕНЬ, относительный_путь), encoding="utf-8") as fh:
        return fh.read()


def _трекаемые():
    итог = subprocess.run(["git", "ls-files"], cwd=КОРЕНЬ,
                          capture_output=True, text=True, check=False)
    if итог.returncode != 0:
        pytest.skip("не git-репозиторий")
    return итог.stdout.splitlines()


class TestОбязательныеДокументы:

    @pytest.mark.parametrize("имя", ОБЯЗАТЕЛЬНЫЕ_ФАЙЛЫ)
    def test_файл_существует(self, имя):
        assert os.path.exists(os.path.join(КОРЕНЬ, имя)), f"для публичного репозитория нужен {имя}"

    def test_лицензия_разделяет_код_и_данные(self):
        текст = _прочитать("LICENSE")
        assert "MIT License" in текст
        assert "DATA-LICENSE.md" in текст, "лицензия обязана отсылать к условиям на данные"
        assert "DISCLAIMER.md" in текст, "safety-предупреждение должно быть видно из лицензии"

    def test_readme_ведёт_к_границам_применения(self):
        текст = _прочитать("README.md")
        for цель in ("DISCLAIMER.md", "LIMITATIONS.md", "DATA-LICENSE.md", "CONTRIBUTING.md"):
            assert цель in текст, f"README не ссылается на {цель}"

    def test_ссылки_readme_не_битые(self):
        текст = _прочитать("README.md")
        битые = []
        for цель in set(re.findall(r"\]\(([^)#]+?)(?:#[^)]*)?\)", текст)):
            if цель.startswith(("http", "mailto", "#")):
                continue
            if not os.path.exists(os.path.join(КОРЕНЬ, цель)):
                битые.append(цель)
        assert not битые, f"битые ссылки в README: {битые}"


class TestЧислаВДокументацииСверены:
    """Числа берутся из данных, а не по памяти — это правило проекта, применённое к себе."""

    def test_счётчик_веществ_в_readme_совпадает_с_базой(self, substances):
        текст = _прочитать("README.md")
        assert f"**{len(substances)} веществ**" in текст, \
            f"в README должно стоять актуальное число веществ ({len(substances)})"

    def test_счётчик_чанков_в_readme_совпадает_с_корпусом(self):
        путь = os.path.join(DATA, "corpus_full_clean.json")
        if not os.path.exists(путь):
            pytest.skip("нет корпуса")
        with io.open(путь, encoding="utf-8") as fh:
            чанков = len(json.load(fh)["chunks"])
        текст = _прочитать("README.md")
        # Допускаем оба написания: «25 970» и «25970».
        варианты = {str(чанков), f"{чанков:,}".replace(",", " "), f"{чанков:,}".replace(",", " ")}
        assert any(в in текст for в in варианты), \
            f"в README должно стоять актуальное число чанков ({чанков})"

    def test_градация_полноты_в_readme_совпадает_с_дашбордом(self, substances):
        import hygiene
        градация = hygiene.quality_dashboard(substances)["data_grade"]
        текст = _прочитать("README.md")
        assert str(градация["passport"]) in текст, \
            "число паспортных записей в README разошлось с /quality"


class TestГигиенаТрекаемыхФайлов:

    def test_env_не_трекается(self):
        утечки = [f for f in _трекаемые()
                  if re.search(r"(^|/)\.env", f)
                  and not re.search(r"\.env\.(example|sample|template)$", f)]
        assert not утечки, f".env в индексе: {утечки}"

    def test_рантайм_состояние_не_трекается(self):
        запрещено = ("data/audit_log.jsonl", "screenshots/", ".playwright-mcp/",
                     ".claude/", ".codex/")
        утечки = [f for f in _трекаемые() if f.startswith(запрещено)]
        assert not утечки, f"рантайм-состояние в индексе: {утечки}"

    def test_секретов_в_трекаемых_файлах_нет(self):
        итог = subprocess.run(
            ["git", "grep", "-lE",
             r"sk-ant-[A-Za-z0-9-]{20,}|sk-or-v1-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"
             r"gh[pousr]_[A-Za-z0-9]{20,}|BEGIN (RSA|OPENSSH|DSA|EC) PRIVATE KEY",
             "--", ".", ":!scripts/guard.sh", ":!tests/test_repo_public_readiness.py"],
            cwd=КОРЕНЬ, capture_output=True, text=True, check=False)
        assert итог.returncode != 0, f"похоже на секрет в: {итог.stdout.strip()}"

    def test_сторож_исполняемый(self):
        assert os.access(os.path.join(КОРЕНЬ, "scripts/guard.sh"), os.X_OK), \
            "scripts/guard.sh должен быть исполняемым — иначе git-хук не сработает"


class TestОбещанияДокументовПодкрепленыКодом:
    """Документ, обещающий команду, обязан обещать существующую команду."""

    def test_упомянутые_в_makefile_скрипты_существуют(self):
        текст = _прочитать("Makefile")
        for путь in re.findall(r"(engine/[\w_]+\.py|scripts/[\w_]+\.sh)", текст):
            assert os.path.exists(os.path.join(КОРЕНЬ, путь)), \
                f"Makefile ссылается на несуществующий {путь}"

    def test_обезличивание_описано_и_реализовано(self):
        assert "anonymize_plants.py" in _прочитать("DATA-LICENSE.md")
        assert os.path.exists(os.path.join(КОРЕНЬ, "engine/anonymize_plants.py"))

    def test_requirements_разделены_по_назначению(self):
        for имя in ("core.txt", "dev.txt", "full.txt"):
            assert os.path.exists(os.path.join(КОРЕНЬ, "requirements", имя))
        assert "-r core.txt" in _прочитать("requirements/dev.txt")
