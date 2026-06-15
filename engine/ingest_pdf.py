# -*- coding: utf-8 -*-
"""
PDF-ингест: грязные данные предприятия (Ступень-1, аудит-спринт).
Это и есть «грабля, за которую платят»: реальные паспорта/ГН часто — СКАНЫ без текстового
слоя, OCR обязателен.

Пайплайн:
  1. Детект текстового слоя (pdfplumber/PyMuPDF). Есть текст -> берём напрямую.
  2. Нет текста (скан) -> растеризуем страницу (PyMuPDF, без системного poppler) -> OCR.
  3. OCR — easyocr (torch/MPS, русский+англ), on-prem, без облака.
  4. Отчёт по качеству: доля страниц со слоем, средняя длина OCR, флаги «грязи».

Запуск:  python3 ingest_pdf.py <pdf> [--pages 5] [--dpi 150] [--ocr]
"""
import os, sys, argparse, time
import fitz  # PyMuPDF

_READER = None
def _ocr_reader():
    global _READER
    if _READER is None:
        import easyocr                       # ленивый импорт: пайплайн-детект работает и без OCR
        _READER = easyocr.Reader(["ru", "en"], gpu=True)  # MPS/GPU если доступен
    return _READER

def has_text_layer(doc, sample=12):
    n = doc.page_count
    idxs = [int(i * n / sample) for i in range(sample)]
    hits = sum(1 for i in idxs if doc[i].get_text().strip())
    return hits, len(idxs)

def page_text(doc, i, dpi=150, ocr=False):
    t = doc[i].get_text().strip()
    if t:
        return t, "layer"
    if not ocr:
        return "", "scan(no-ocr)"
    pix = doc[i].get_pixmap(dpi=dpi)
    import numpy as np
    img = np.frombuffer(pix.tobytes("png"), dtype=np.uint8)  # png -> easyocr сам декодирует
    res = _ocr_reader().readtext(pix.tobytes("png"), detail=0, paragraph=True)
    return "\n".join(res), "ocr"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf"); ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--dpi", type=int, default=150); ap.add_argument("--ocr", action="store_true")
    a = ap.parse_args()
    doc = fitz.open(a.pdf)
    hits, sampled = has_text_layer(doc)
    scanned = hits == 0
    print(f"PDF: {a.pdf}  | страниц: {doc.page_count}")
    print(f"текстовый слой: {hits}/{sampled} проб -> {'СКАН (нужен OCR)' if scanned else 'есть текст'}")
    if scanned and not a.ocr:
        print("=> запусти с --ocr для извлечения (easyocr, on-prem). Без OCR скан не читается — это и есть грабля.")
    print("-" * 70)
    lens = []
    for i in range(min(a.pages, doc.page_count)):
        t0 = time.time(); txt, mode = page_text(doc, i, a.dpi, a.ocr); dt = time.time() - t0
        lens.append(len(txt))
        print(f"стр {i} [{mode}, {dt:.1f}s, {len(txt)} симв]: {txt[:160].replace(chr(10),' ')!r}")
    print("-" * 70)
    avg = sum(lens) / len(lens) if lens else 0
    print(f"средняя длина извлечения: {avg:.0f} симв/стр")
    if scanned:
        print("ВЫВОД (аудит-спринт): документ — скан, текстовый слой отсутствует. Прод-ингест "
              "реальных паспортов завода потребует OCR-стадии + ручной верификации (грязь, таблицы).")

if __name__ == "__main__":
    main()
