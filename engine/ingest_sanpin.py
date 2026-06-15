# -*- coding: utf-8 -*-
"""
Bulk-ингест таблицы 2.1 СанПиН 1.2.3685-21 (ПДК вредных веществ в воздухе рабочей зоны)
из официального PDF -> наша схема веществ -> пересборка базы с 48 до полного перечня.

ЗАПУСКАЕТСЯ НА МАШИНЕ ИЛЬИ (у песочницы агента нет сети и доступа к PDF).

Шаги:
  1. Скачать официальный PDF (Роспотребнадзор) или взять локальную копию.
  2. python ingest_sanpin.py --pdf ./SanPiN_1.2.3685-21.pdf
  3. python ingest_sanpin.py --pdf ./SanPiN... --merge --rebuild   # слить с базой и пересобрать корпус+UI

ВАЖНО (safety): ПДК это здоровье людей. Скрипт ставит confidence='needs_review' на всё,
что вытащил из PDF. Перед prod-использованием прогнать review-лист глазами по тексту СанПиН.

Зависимости (на машине Ильи):  pip install pdfplumber
"""
import json, os, re, argparse, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")

# Заголовки колонок таблицы 2.1 (фаззи-детект, порядок/формулировки в PDF плавают)
COLMAP = {
    "name":  ["наименование"],
    "formula": ["формула"],
    "cas":   ["cas", "регистрационный номер", "номер cas"],
    "pdk":   ["пдк", "величина", "мг/м"],
    "class": ["класс опасности", "класс"],
    "state": ["агрегатное", "состояние"],
    "note":  ["особенности", "действия"],
}

def detect_columns(header_row):
    """По строке-заголовку определить индекс каждой нашей колонки."""
    idx = {}
    for i, cell in enumerate(header_row):
        c = (cell or "").lower().replace("\n", " ")
        for key, keys in COLMAP.items():
            if key in idx: continue
            if any(k in c for k in keys):
                idx[key] = i
    return idx

def clean(x):
    return re.sub(r"\s+", " ", (x or "").replace("\n", " ")).strip()

def parse_pdk(raw):
    """Из ячейки ПДК достать число/диапазон в мг/м3 (макс или макс/среднесменная)."""
    s = clean(raw).replace(",", ".")
    m = re.findall(r"\d+\.?\d*", s)
    if not m: return None
    if "/" in s and len(m) >= 2:
        return f"{m[0]}/{m[1]}"
    return m[0]

def parse_class(raw):
    m = re.search(r"[1-4]", clean(raw))
    return m.group(0) if m else None

def rows_to_substances(rows, colidx):
    out = []
    for r in rows:
        if len(r) <= max(colidx.values(), default=0): continue
        name = clean(r[colidx["name"]]) if "name" in colidx else ""
        if not name or len(name) < 2 or name.lower().startswith(("наименование", "№")):
            continue
        if not re.search(r"[а-яё]", name.lower()):  # не вещество (мусорная строка)
            continue
        s = {
            "name": name.lower(),
            "formula": clean(r[colidx["formula"]]) if "formula" in colidx else "",
            "cas": clean(r[colidx["cas"]]) if "cas" in colidx else "",
            "pdk_mgm3": parse_pdk(r[colidx["pdk"]]) if "pdk" in colidx else None,
            "hazard_class": parse_class(r[colidx["class"]]) if "class" in colidx else None,
            "ghs": [], "storage": "", "ppe": "", "first_aid": "",
            "flash_point_c": None,
            "special": clean(r[colidx["note"]]) if "note" in colidx else "",
            "source_tier": "T1", "confidence": "needs_review",
        }
        out.append(s)
    return out

def ingest_html(html_path):
    """Парс таблицы ГН/СанПиН из сохранённой HTML-страницы (meganorm/garant): текстовый слой, без OCR."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        sys.exit("Установите HTML-парсер:  pip install beautifulsoup4 lxml")
    html = open(html_path, encoding="utf-8", errors="ignore").read()
    soup = BeautifulSoup(html, "lxml")
    subs = []
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [clean(td.get_text(" ")) for td in tr.find_all(["td", "th"])]
            if cells: rows.append(cells)
        if len(rows) < 3: continue
        # ищем строку-заголовок (где есть наименование и ПДК)
        hdr_i = None
        for i, r in enumerate(rows[:6]):
            ci = detect_columns(r)
            if "name" in ci and "pdk" in ci:
                hdr_i, colidx = i, ci; break
        if hdr_i is None: continue
        subs += rows_to_substances(rows[hdr_i+1:], colidx)
    seen, uniq = set(), []
    for s in subs:
        k = s["name"].strip().lower()
        if k in seen or len(k) < 2: continue
        seen.add(k); uniq.append(s)
    print(f"из HTML извлечено веществ (уник): {len(uniq)}")
    return uniq

def ingest(pdf_path):
    try:
        import pdfplumber
    except ImportError:
        sys.exit("Установите парсер таблиц:  pip install pdfplumber")
    subs, pages_with_table = [], 0
    with pdfplumber.open(pdf_path) as pdf:
        for pageno, page in enumerate(pdf.pages):
            for tbl in (page.extract_tables() or []):
                if not tbl or len(tbl) < 2: continue
                colidx = detect_columns(tbl[0])
                if "name" not in colidx or "pdk" not in colidx:  # не та таблица
                    continue
                pages_with_table += 1
                subs += rows_to_substances(tbl[1:], colidx)
    # дедуп по имени
    seen, uniq = set(), []
    for s in subs:
        k = s["name"].strip().lower()
        if k in seen: continue
        seen.add(k); uniq.append(s)
    print(f"страниц с таблицей ПДК: {pages_with_table}, извлечено веществ (уник): {len(uniq)}")
    return uniq

def merge_into_base(new):
    base = json.load(open(os.path.join(DATA, "substances.json"), encoding="utf-8"))
    core = json.load(open(os.path.join(DATA, "substances_core.json"), encoding="utf-8"))
    have = {s["name"].strip().lower() for s in base + core}
    added = [s for s in new if s["name"].strip().lower() not in have]
    json.dump(new, open(os.path.join(DATA, "substances_sanpin.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    # объединённый файл-источник для корпуса (verified ядро + sanpin-наполнение)
    allsubs = base + core + added
    json.dump(allsubs, open(os.path.join(DATA, "substances_bulk.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    review = [s["name"] for s in added if not s.get("pdk_mgm3") or not s.get("hazard_class")]
    print(f"в базе уже: {len(have)}, новых из СанПиН: {len(added)}, итого: {len(allsubs)}")
    print(f"НА РЕВЬЮ (пустой ПДК или класс): {len(review)} веществ -> data/substances_sanpin.json")
    print("Safety: все sanpin-записи помечены confidence='needs_review'. Сверить ПДК глазами.")
    return added

def selftest():
    """Прогон логики парсинга на синтетической таблице (без PDF), чтобы проверить схему."""
    fake_header = ["№", "Наименование вещества", "Формула", "Величина ПДК, мг/м3", "Класс опасности", "Особенности"]
    fake_rows = [
        ["1", "Ацетальдегид", "C2H4O", "5", "3", "раздражающее"],
        ["2", "Хлор", "Cl2", "1", "2", "остронаправленное"],
        ["3", "Ртути дихлорид", "HgCl2", "0,2 / 0,05", "1", "аллерген"],
    ]
    colidx = detect_columns(fake_header)
    subs = rows_to_substances(fake_rows, colidx)
    print("SELF-TEST detect_columns:", colidx)
    for s in subs:
        print(f"  {s['name']:18} ПДК={s['pdk_mgm3']} класс={s['hazard_class']} conf={s['confidence']}")
    assert len(subs) == 3 and subs[2]["pdk_mgm3"] == "0.2/0.05" and subs[1]["hazard_class"] == "2"
    print("SELF-TEST OK: парсер строит корректную схему. На реальном PDF проверить отдельно (UNVERIFIED).")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", help="путь к официальному PDF СанПиН 1.2.3685-21")
    ap.add_argument("--html", help="путь к сохранённой HTML-странице ГН/СанПиН (meganorm/garant), РЕКОМЕНДУЕТСЯ")
    ap.add_argument("--merge", action="store_true", help="слить с базой в substances_bulk.json")
    ap.add_argument("--rebuild", action="store_true", help="пересобрать корпус и UI после merge")
    ap.add_argument("--selftest", action="store_true", help="проверить логику парсинга без PDF")
    a = ap.parse_args()
    if a.selftest:
        selftest(); sys.exit(0)
    if a.html:
        new = ingest_html(a.html)
    elif a.pdf:
        new = ingest(a.pdf)
    else:
        sys.exit("Укажите --html путь_к_странице.htm (рекомендуется) или --pdf путь.pdf, либо --selftest")
    json.dump(new, open(os.path.join(DATA, "substances_sanpin.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    if a.merge:
        merge_into_base(new)
    if a.rebuild:
        os.system(f"cd {HERE} && python3 corpus.py && python3 generate_ui.py")
        print("Корпус и UI пересобраны на расширенной базе.")
