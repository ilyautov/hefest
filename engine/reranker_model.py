# -*- coding: utf-8 -*-
"""
Кросс-энкодер реранкер (BAAI/bge-reranker-v2-m3) на torch+MPS (Metal-GPU, M1 Max).
Грузится напрямую через transformers, без sentence-transformers (тот тянет torchcodec
-> требует ffmpeg/libavutil, которого нет). bge-reranker-v2-m3 = XLM-RoBERTa-классификатор:
для пары (запрос, пассаж) выдаёт логит релевантности. Реранк top-N кандидатов из
семантического retrieval тянет правильное вещество из top-3 в top-1.
On-prem: модель локальная, данные не уходят.
"""
import os
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")

def _device():
    if torch.backends.mps.is_available(): return "mps"
    if torch.cuda.is_available(): return "cuda"
    return "cpu"

class CrossEncoderReranker:
    def __init__(self, model=MODEL, device=None, max_len=512):
        self.device = device or _device()
        self.max_len = max_len
        self.tok = AutoTokenizer.from_pretrained(model)
        self.model = AutoModelForSequenceClassification.from_pretrained(model).to(self.device).eval()

    @torch.no_grad()
    def scores(self, query, passages, batch_size=16):
        out = []
        for i in range(0, len(passages), batch_size):
            chunk = passages[i:i + batch_size]
            enc = self.tok([query] * len(chunk), chunk, padding=True, truncation=True,
                           max_length=self.max_len, return_tensors="pt").to(self.device)
            logits = self.model(**enc).logits.view(-1).float().cpu()
            out.extend(logits.tolist())
        return out

    def rerank(self, query, candidates, top_k=3, text_key="text"):
        """candidates: список dict с полем text_key. Возвращает top_k по убыванию релевантности."""
        if not candidates: return []
        sc = self.scores(query, [c[text_key] for c in candidates])
        order = sorted(range(len(candidates)), key=lambda i: sc[i], reverse=True)
        return [(candidates[i], float(sc[i])) for i in order[:top_k]]

_SINGLETON = None
def get_reranker():
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = CrossEncoderReranker()
    return _SINGLETON

if __name__ == "__main__":
    r = CrossEncoderReranker()
    q = "антидот при отравлении цианидом"
    docs = [
        {"text": "Меры первой помощи при отравлении цианидом: амилнитрит, тиосульфат натрия, гидроксокобаламин."},
        {"text": "Серная кислота: при попадании на кожу промыть большим количеством воды."},
        {"text": "Цианид натрия: класс опасности 1, остронаправленный механизм действия."},
    ]
    for c, s in r.rerank(q, docs, top_k=3):
        print(f"{s:+.3f}  {c['text'][:60]}")
