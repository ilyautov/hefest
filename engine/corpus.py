# -*- coding: utf-8 -*-
"""
Генерация реального корпуса паспортов безопасности (SDS) по структуре ГОСТ 30333-2022
(16 разделов; ранее 30333-2007 — каркас разделов идентичен) из структурированных
регуляторных данных + линковка с заводами ТПП Дзержинска.
Выход: corpus_full.json (чанки по разделам), substances_all.json, plants_linked.json.
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")

def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)

# Алиасы для линковки названий заводов с карточками веществ
ALIASES = {
    "этиленоксид": "окись этилена", "окись этилена": "окись этилена",
    "синильная кислота": "циановодород (синильная кислота)",
    "циановодород": "циановодород (синильная кислота)",
    "изоцианаты": "толуилендиизоцианат (ТДИ)",
    "серный ангидрид": "серный ангидрид (триоксид серы)",
    "перекись водорода": "перекись водорода", "пероксид водорода": "перекись водорода",
    "цианид натрия": "цианид натрия", "цианид калия": "цианид калия",
    "оксид углерода": "оксид углерода",
}

def norm(n):
    n = n.strip().lower()
    return ALIASES.get(n, n).strip().lower()

def hazard_label(hc):
    return {"1":"1 (чрезвычайно опасное)","2":"2 (высокоопасное)","3":"3 (умеренно опасное)","4":"4 (малоопасное)"}.get(str(hc), "не установлен")

def fmt_pdk(p):
    if not p: return "не установлена в действующих ГН (требует уточнения по марке/источнику)"
    return f"{p} мг/м3 в воздухе рабочей зоны"

def build_sections(s):
    """Из структурной карточки вещества собрать разделы паспорта безопасности (ГОСТ 30333)."""
    name, f, cas = s["name"], s.get("formula",""), s.get("cas","")
    fp = s.get("flash_point_c")
    ghs = ", ".join(s.get("ghs", [])) or "см. классификацию по ГОСТ 12.1.007"
    sec = {}
    sec["Раздел 1. Идентификация вещества"] = (
        f"{name}. Химическая формула {f}, регистрационный номер CAS {cas}. "
        f"Класс опасности по ГОСТ 12.1.007: {hazard_label(s.get('hazard_class'))}. "
        f"Уровень достоверности данных: {s.get('confidence','n/a')}, источник {s.get('source_tier','n/a')}.")
    sec["Раздел 2. Идентификация опасности"] = (
        f"Основные виды опасности {name}: {ghs}. "
        f"Особые указания: {s.get('special','нет дополнительных указаний')}.")
    sec["Раздел 4. Меры первой помощи"] = (
        f"Первая помощь при воздействии {name}: {s.get('first_aid','промыть водой, обеспечить свежий воздух, обратиться за медицинской помощью')}.")
    fire = "Негорючее вещество." if fp is None else f"Температура вспышки около {fp} градусов Цельсия."
    sec["Раздел 5. Меры пожаротушения"] = (
        f"{fire} {('Пары могут образовывать с воздухом взрывоопасные смеси. ' if (isinstance(fp,(int,float)) and fp < 60) else '')}"
        f"Учитывать особые свойства: {s.get('special','')}.")
    sec["Раздел 6. Меры при аварийном выбросе"] = (
        f"При разливе или утечке {name} изолировать зону, удалить персонал, надеть СИЗ ({s.get('ppe','средства защиты кожи и органов дыхания')}). "
        f"Собрать инертным сорбентом в герметичную тару, не допускать попадания в канализацию и водоёмы.")
    sec["Раздел 7. Обращение и хранение"] = (
        f"Хранение и обращение с {name}: {s.get('storage','хранить в герметичной таре в вентилируемом помещении вдали от несовместимых веществ')}.")
    sec["Раздел 8. Средства защиты (СИЗ) и контроль"] = (
        f"ПДК: {fmt_pdk(s.get('pdk_mgm3'))}. "
        f"Средства индивидуальной защиты: {s.get('ppe','перчатки, защитные очки, при необходимости респиратор')}. "
        f"Обеспечить вентиляцию и контроль концентрации в воздухе рабочей зоны.")
    sec["Раздел 9. Физико-химические свойства"] = (
        f"{name}, формула {f}. " + (f"Температура вспышки около {fp} градусов Цельсия. " if fp is not None else "") +
        "Прочие свойства уточняются по марке продукта.")
    sec["Раздел 10. Стабильность и реакционная способность"] = (
        f"Несовместимости и реакционная способность {name}: {s.get('storage','')}. Особо: {s.get('special','')}.")
    sec["Раздел 11. Токсикологическая информация"] = (
        f"ПДК {name} в воздухе рабочей зоны: {fmt_pdk(s.get('pdk_mgm3'))}. "
        f"Класс опасности {hazard_label(s.get('hazard_class'))}. Опасности: {ghs}.")
    return sec

def main():
    # если есть расширенная база из СанПиН-ингеста — берём её, иначе verified-ядро
    if os.path.exists(os.path.join(DATA, "substances_bulk.json")):
        src = load("substances_bulk.json")
        print("источник: substances_bulk.json (verified ядро + СанПиН-ингест)")
    else:
        src = load("substances.json") + load("substances_core.json")
        print("источник: verified ядро (substances.json + substances_core.json)")
    # дедуп по нормализованному имени
    seen, subs = set(), []
    for s in src:
        key = s["name"].strip().lower()
        if key in seen: continue
        seen.add(key); subs.append(s)
    by_name = {s["name"].strip().lower(): s for s in subs}

    # чанки
    chunks = []
    for s in subs:
        for sec, text in build_sections(s).items():
            chunks.append({
                "doc_id": s["name"], "substance": s["name"], "formula": s.get("formula",""),
                "cas": s.get("cas",""), "hazard_class": s.get("hazard_class"),
                "section": sec, "text": text, "source_tier": s.get("source_tier"),
                "confidence": s.get("confidence"),
                "citation": f'{s["name"]} ({s.get("formula","")}, CAS {s.get("cas","")}), {sec}'
            })

    # линковка заводов
    plants = load("plants.json")
    sub_keys = set(by_name.keys())
    linked, coverage = [], {"matched":0,"unmatched":0,"unmatched_list":[]}
    for p in plants:
        ms, um = [], []
        for raw in p.get("substances", []):
            k = norm(raw)
            if k in sub_keys:
                ms.append(by_name[k]["name"]); coverage["matched"]+=1
            else:
                um.append(raw); coverage["unmatched"]+=1; coverage["unmatched_list"].append(raw)
        linked.append({**p, "matched_substances": ms, "unmatched_substances": um})

    # обратная связь вещество -> заводы
    sub_to_plants = {}
    for p in linked:
        for m in p["matched_substances"]:
            sub_to_plants.setdefault(m, []).append(p["plant"])

    out_corpus = {"meta":{"standard":"ГОСТ 30333-2022 (структура; каркас разделов как в 30333-2007)","substances":len(subs),
                          "chunks":len(chunks),"nature":"реальные регуляторные данные (ГН 2.2.5/СанПиН), документ-форма сгенерирована"},
                  "chunks":chunks}
    with open(os.path.join(DATA,"corpus_full.json"),"w",encoding="utf-8") as f:
        json.dump(out_corpus,f,ensure_ascii=False)
    with open(os.path.join(DATA,"substances_all.json"),"w",encoding="utf-8") as f:
        json.dump(subs,f,ensure_ascii=False,indent=1)
    with open(os.path.join(DATA,"plants_linked.json"),"w",encoding="utf-8") as f:
        json.dump({"plants":linked,"substance_to_plants":sub_to_plants},f,ensure_ascii=False,indent=1)

    print(f"вещества: {len(subs)}  чанки: {len(chunks)}  заводы: {len(linked)}")
    print(f"линковка завод->вещество: matched={coverage['matched']} unmatched={coverage['unmatched']}")
    um = sorted(set(coverage["unmatched_list"]))
    print(f"непокрытые вещества заводов ({len(um)}): {', '.join(um[:25])}")

if __name__ == "__main__":
    main()
