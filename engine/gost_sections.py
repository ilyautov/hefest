# -*- coding: utf-8 -*-
"""
Карта соответствия выдачи 16 разделам паспорта безопасности по ГОСТ 30333.

Идея: ГОСТ 30333 задаёт жёсткую структуру паспорта из 16 разделов. Мы НЕ генерируем паспорт —
мы показываем, какой раздел ЧЕМ у нас закрыт (какой слой данных / какое поле / какой источник),
с провенансом, и где ЧЕСТНЫЙ ПРОБЕЛ. Это и есть «приведение к ГОСТ»: не переделка, а карта покрытия.

ПРИНЦИП БЕЗОПАСНОСТИ:
  * структура 16 разделов — стандарт (ГОСТ 30333 / СГС Annex 4), един во всех источниках;
  * ТОЧНЫЕ ФОРМУЛИРОВКИ названий разделов взяты из вторичных источников и помечены
    title_needs_review=True — финально сверить с оригиналом ГОСТ 30333-2022 PDF перед поставкой;
  * мы НЕ выдумываем содержимое разделов — только маршрутизируем уже собранные данные.

status раздела:
  full    — есть структурированные данные нашего слоя;
  partial — частично (часть из корпуса/типового по группе, нужна сверка эксперта);
  corpus  — закрывается только полнотекстовым поиском по паспорту (нет отдельного слоя);
  gap     — структурного источника нет (честно показываем дыру);
  na      — поле конкретной партии/поставки, вне справочной системы by design.
"""
import normative

# Формулировки названий — ТОЧНЫЕ цитаты п. 5.1 ГОСТ 30333-2022, сверены по двум источникам с полным
# читаемым текстом стандарта (allgosts.ru/13/100/gost_30333-2022 и meganorm.ru, совпадают по всем 16),
# плюс третий (lakokraska-ya.ru) подтверждает структуру/порядок. Поэтому title_needs_review=False.
SECTIONS = [
    {"n": 1,  "title": "Идентификация химической продукции и сведения об изготовителе и/или "
                       "уполномоченном изготовителем лице", "short": "Что это за вещество"},
    {"n": 2,  "title": "Идентификация опасности(ей)", "short": "Чем опасно, класс, маркировка"},
    {"n": 3,  "title": "Состав (информация о компонентах)", "short": "Формула, CAS, состав"},
    {"n": 4,  "title": "Меры первой помощи", "short": "Что делать при поражении"},
    {"n": 5,  "title": "Меры и средства обеспечения пожаровзрывобезопасности", "short": "Тушение, пределы"},
    {"n": 6,  "title": "Меры по предотвращению и ликвидации аварийных и чрезвычайных ситуаций",
     "short": "Разлив, ЧС, зоны"},
    {"n": 7,  "title": "Правила хранения химической продукции и обращения с ней при "
                       "погрузочно-разгрузочных работах", "short": "Хранение, совместимость"},
    {"n": 8,  "title": "Средства контроля за опасным воздействием и средства индивидуальной защиты",
     "short": "ПДК, СИЗ"},
    {"n": 9,  "title": "Физико-химические свойства", "short": "Вспышка, кипение, плотность…"},
    {"n": 10, "title": "Стабильность и реакционная способность", "short": "Несовместимость, реакции"},
    {"n": 11, "title": "Информация о токсичности", "short": "Действие на организм"},
    {"n": 12, "title": "Информация о воздействии на окружающую среду", "short": "Экологические ПДК"},
    {"n": 13, "title": "Рекомендации по удалению отходов (остатков)", "short": "Утилизация"},
    {"n": 14, "title": "Информация при перевозках (транспортировании)", "short": "Номер ООН, ДОПОГ"},
    {"n": 15, "title": "Информация о национальном и международном законодательствах", "short": "Применимые акты"},
    {"n": 16, "title": "Дополнительная информация", "short": "Синонимы, источники, оговорки"},
]

TITLE_NEEDS_REVIEW = False  # сверено с п. 5.1 ГОСТ 30333-2022 по 2+ источникам с полным текстом


def _gval(g, key):
    """guidance хранит поля как {value, source}; вернуть строку value либо None."""
    v = (g or {}).get(key)
    if isinstance(v, dict):
        return v.get("value")
    return v if isinstance(v, str) else None


def _clip(t, n=120):
    return t[:n] + ("…" if len(t) > n else "")


def _probe(n, out):
    """Возвращает (status, filled_by:list[str], source:str|None, note:str|None) для раздела n."""
    s = out
    g = (out.get("guidance") or {})

    if n == 1:  # идентификация + производитель
        have = [x for x in [
            f"наименование: {s['name']}" if s.get("name") else None,
            f"CAS {s['cas']}" if s.get("cas") else None,
        ] if x]
        # сведения о производителе — поле конкретной партии, у нас их нет by design
        return ("partial", have, "база веществ",
                "Сведения о производителе/поставщике — реквизиты конкретной партии, берутся из самого "
                "паспорта поставщика, в справочной системе их нет (by design).")

    if n == 2:  # идентификация опасности
        have = []
        src = []
        if s.get("hazard_class"):
            have.append(f"класс опасности {s['hazard_class']} (ГОСТ 12.1.007)"); src.append("ГОСТ 12.1.007-76")
        if s.get("pubchem") or s.get("ghs"):
            have.append("СГС: пиктограммы, сигнальное слово, H-фразы"); src.append("ГОСТ 31340-2013 / PubChem")
        if s.get("sanpin"):
            have.append("особые отметки СанПиН (канцероген/аллерген/кожа и т.д.)")
        if have:
            return ("full", have, "; ".join(dict.fromkeys(src)) or None, None)
        return ("gap", [], None, "Класс/маркировка не определены для вещества.")

    if n == 3:  # состав
        have = [x for x in [
            f"формула {s['formula']}" if s.get("formula") else None,
            f"CAS {s['cas']}" if s.get("cas") else None,
        ] if x]
        if have:
            return ("partial", have, "база веществ",
                    "Состав смесей (компоненты и их доли) — из паспорта поставщика; здесь идентификация вещества.")
        return ("gap", [], None, None)

    if n == 4:  # первая помощь
        if s.get("first_aid"):
            return ("full", [_clip(s["first_aid"])], "паспорт", None)
        gv = _gval(g, "first_aid")
        if gv:
            return ("partial", [_clip(gv)], "типовое по группе",
                    "Первая помощь — типовая по группе, не из паспорта вещества. Требует сверки.")
        return ("gap", [], None, None)

    if n == 5:  # пожаровзрывобезопасность
        ph = s.get("physchem")
        have = []
        if s.get("flash_point_c") not in (None, ""):
            have.append(f"темп. вспышки {s['flash_point_c']} °C")
        if ph:
            keys = {p["key"] for p in ph.get("props", [])}
            if "flash_point" in keys: have.append("темп. вспышки (PubChem)")
            if "flammable_limits" in keys: have.append("пределы воспламенения НКПР/ВКПР")
        if have:
            return ("partial", have, "PubChem / паспорт",
                    "Огнетушащие средства и тактика тушения — в полном тексте паспорта (корпус). "
                    "Здесь — физ. параметры пожароопасности.")
        return ("corpus", [], None, "Меры пожаротушения — полнотекстовый поиск по паспорту.")

    if n == 6:  # аварийные ситуации
        have = []
        src = []
        if s.get("idlh"):
            have.append("IDLH (порог немедленной опасности)"); src.append("NIOSH")
        tr = s.get("transport") or {}
        uns = sorted({u.get("un") for u in (tr.get("un") or []) if u.get("un")})
        if uns:
            have.append("ООН " + ", ".join(uns) + " + аварийная карта ERG")
        # зоны заражения АХОВ — через /emergency (РД 52.04.253)
        have.append("аварийная карточка /emergency (зоны заражения РД 52.04.253 — для АХОВ)")
        return ("partial", have, "; ".join(src) or "система",
                "Зоны эвакуации/заражения считаются для АХОВ (РД 52.04.253-90, needs_review).")

    if n == 7:  # хранение
        if s.get("storage"):
            return ("full", [_clip(s["storage"])], "паспорт", None)
        gv = _gval(g, "storage")
        if gv:
            return ("partial", [_clip(gv)], "типовое по группе",
                    "Условия хранения — типовые по группе. Требует сверки.")
        return ("gap", [], None, None)

    if n == 8:  # контроль + СИЗ
        have = []
        src = []
        if s.get("pdk_mgm3"):
            have.append(f"ПДК раб. зоны {s['pdk_mgm3']} мг/м³"); src.append("СанПиН 1.2.3685-21")
        if s.get("ppe") or g.get("ppe"):
            have.append("СИЗ" + ("" if s.get("ppe") else " (типовые по группе)"))
        if s.get("idlh"):
            have.append("IDLH")
        if have:
            return ("full" if s.get("pdk_mgm3") and s.get("ppe") else "partial",
                    have, "; ".join(src) or None, None)
        return ("gap", [], None, None)

    if n == 9:  # физхимия
        ph = s.get("physchem")
        if ph and ph.get("props"):
            labels = [p["label"] for p in ph["props"]]
            return ("full", labels, ph.get("source", "PubChem"), None)
        return ("gap", [], None, "Физико-химические свойства не подтянуты для вещества.")

    if n == 10:  # стабильность/реакционная способность
        if s.get("special"):
            return ("partial", [s["special"][:120] + ("…" if len(s["special"]) > 120 else "")],
                    "паспорт", "Несовместимость/реакции — из отметок паспорта; полная картина — корпус.")
        return ("corpus", [], None, "Стабильность и реакц. способность — полнотекстовый поиск по паспорту.")

    if n == 11:  # токсичность
        have = []
        if s.get("idlh"): have.append("IDLH (острый порог, NIOSH)")
        if s.get("pdk_mgm3"): have.append("ПДК (хроническое нормирование)")
        if s.get("sanpin"): have.append("отметки СанПиН (канцерогенность/аллергенность и т.п.)")
        if have:
            return ("partial", have, "NIOSH / СанПиН",
                    "Числовые токсикологические данные (LD50/LC50) — в корпусе паспорта, отдельного слоя нет.")
        return ("corpus", [], None, "Токсикология — полнотекстовый поиск по паспорту.")

    if n == 12:  # окружающая среда
        env = s.get("sanpin_env")
        if env:
            have = []
            if env.get("atmo"): have.append("ПДК атмосферы населённых мест")
            if env.get("water"): have.append("ПДК воды")
            return ("full", have or ["экологические ПДК"], "СанПиН 1.2.3685-21", None)
        return ("gap", [], None, "Экологические ПДК (атмосфера/вода) не найдены для вещества.")

    if n == 13:  # отходы
        w = s.get("waste")
        if w and w.get("measures"):
            return ("partial", w["measures"][:2], "типовое по группе + ФККО/89-ФЗ",
                    "Меры типовые по группе. Класс отхода (I–V) и код ФККО — эколог предприятия "
                    "(Приказ Минприроды № 536). Не из паспорта — сверьте.")
        return ("gap", [], None, "Удаление отходов — нет данных по веществу.")

    if n == 14:  # транспортировка
        tr = s.get("transport") or {}
        uns = sorted({u.get("un") for u in (tr.get("un") or []) if u.get("un")})
        if uns:
            have = ["номер ООН " + ", ".join(uns)]
            if tr.get("labels"): have.append("метки опасности / ДОПОГ-класс")
            erg = sorted({u.get("erg_guide") for u in (tr.get("un") or []) if u.get("erg_guide")})
            if erg: have.append("ERG " + ", ".join(erg))
            return ("full", have, tr.get("source", "PubChem"), tr.get("note"))
        if s.get("un_number"):
            return ("partial", [f"номер ООН {s['un_number']}"], "АХОВ-карточка", None)
        return ("gap", [], None, "Номер ООН/транспортная классификация не найдены.")

    if n == 15:  # законодательство
        acts = normative.applicable_for(s)
        if acts:
            return ("full", [a["id"] for a in acts], "реестр нормативки", None)
        return ("partial", ["ГОСТ 30333-2022"], "реестр нормативки", None)

    if n == 16:  # доп. информация
        have = []
        if s.get("synonyms"): have.append(f"синонимы ({len(s['synonyms'])})")
        if s.get("source_tier"): have.append(f"источник tier {s['source_tier']}")
        have.append("статус экспертной проверки (verification)")
        return ("partial", have, "система", None)

    return ("gap", [], None, None)


def coverage_for(out):
    """
    out — собранный словарь из /substance.
    Возвращает {sections:[{n,title,short,status,filled_by,source,note}], summary:{...}, title_needs_review}.
    """
    sections = []
    counts = {}
    for sec in SECTIONS:
        status, filled, source, note = _probe(sec["n"], out)
        counts[status] = counts.get(status, 0) + 1
        sections.append({
            "n": sec["n"], "title": sec["title"], "short": sec["short"],
            "status": status, "filled_by": filled, "source": source, "note": note,
        })
    # «закрыто структурно» = full + partial (есть хоть какие-то наши данные)
    structured = counts.get("full", 0) + counts.get("partial", 0)
    return {
        "sections": sections,
        "title_needs_review": TITLE_NEEDS_REVIEW,
        "summary": {
            "total": len(SECTIONS),
            "full": counts.get("full", 0),
            "partial": counts.get("partial", 0),
            "corpus": counts.get("corpus", 0),
            "gap": counts.get("gap", 0),
            "na": counts.get("na", 0),
            "structured": structured,
        },
        "standard": "ГОСТ 30333-2022 (структура; формулировки названий — на сверке с оригиналом)",
    }
