[English] · [Русский](README.md)

# HEFEST — a RAG assistant for chemical safety data sheets (Russian regulatory domain)

[![tests](https://github.com/ilyautov/hefest/actions/workflows/ci.yml/badge.svg)](https://github.com/ilyautov/hefest/actions/workflows/ci.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10--3.13-blue.svg)](https://www.python.org/)

> **HEFEST** (Hephaestus, the smith god): out of a heap of PDF safety data sheets the system
> forges a verifiable substance card. *Answers from the sheet, stays silent when unsure, the
> signature belongs to a human.*

A plain-language question — "antidote for cyanide poisoning", "how to store sulfuric acid",
"what is hazardous at this site" — returns an answer naming the substance, the section of the
safety data sheet (structured per **GOST 30333-2022**), CAS number, hazard class and the
confidence level of the source. Everything runs offline, inside the plant's own perimeter.

**The interface, the data and the documentation are in Russian.** The domain is Russian
occupational-safety regulation (GN 2.2.5, SanPiN 1.2.3685-21, GOST 12.1.007-76), so the project
is written for the people who work with it. This page exists so an English-speaking reader can
judge whether the engineering is interesting to them.

> [!WARNING]
> **This is decision support, not a certified safety data sheet.** The cost of an error here is
> human health. Read [`DISCLAIMER.md`](DISCLAIMER.md) and [`LIMITATIONS.md`](LIMITATIONS.md)
> before any use beyond a demo. Both are in Russian; the short version is that the shipped
> database is a demonstration corpus, most records are unsigned by any expert, and the document
> form of the sheets is generated rather than digitised from real plant documents.

## What is engineering-interesting here

A conventional RAG system, when it hits a gap in its data, produces plausible text. In
industrial safety that is unacceptable. The whole design is organised around one rule:
**regulatory values are never invented**. In practice that yields four observable properties,
each pinned by a test:

| Property | How to observe it |
|---|---|
| **Abstains instead of fabricating.** An out-of-domain question gets an honest refusal, not an invented answer. | `POST /ask` with an unrelated question → `"abstained": true`, `"sources": []` |
| **Never converts units.** ppm is not turned into mg/m³: an exposure ratio is computed only when units match, otherwise the user is told to check manually. | `GET /shift/хлор?value=15&unit=ppm` → `"pdk_ratio": null` |
| **Never passes generic guidance off as sheet-specific.** Values derived from a chemical group are graded `baseline` and carry a disclaimer. | `GET /quality` → `data_grade: {passport: 52, baseline: 2545}` |
| **Shows gaps instead of filling them.** No data means "no data"; a waste hazard class is not assigned when indicators are missing. | `POST /waste/estimate` → `"class": null`, `"confidence": "insufficient_data"` |

A fifth property is the identifier integrity check: CAS numbers are validated by their check
digit at read time, invalid ones are flagged on the card, and enrichment is **not** joined on
them — so a typo cannot silently pull another substance's hazard data onto the page. The
system deliberately does **not** guess the corrected number: substituting a plausible
identifier would itself be fabrication.

## Quick start

```bash
git clone https://github.com/ilyautov/hefest.git && cd hefest
python3 -m pip install -r requirements/dev.txt
make run          # service on http://127.0.0.1:8012
make test         # 77 offline tests: no Ollama, no network, no prebuilt index
```

The lexical mode works out of the box — no model, no API keys, no network, and no need to pull
the ~106 MB embedding file from Git LFS. The semantic mode (noticeably better retrieval) needs
a local Ollama with `bge-m3` and `qwen2.5:7b`: `make run-semantic`. If the embeddings are
absent the service degrades to lexical retrieval instead of failing.

## Stack

FastAPI (43 endpoints) and 12 static HTML screens with no build step. Retrieval is pluggable:
lexical hybrid (char + word TF-IDF and BM25), semantic (numpy over bge-m3 embeddings), or
Qdrant. Generation is extractive by default — zero hallucination risk — and optionally
grounded generation through a local `qwen2.5:7b` at temperature 0. An optional cross-encoder
reranker (`bge-reranker-v2-m3`) is loaded lazily.

Measured on 47 queries: lexical top-1 60% → semantic 84% → with reranking 92%. Those numbers
demonstrate that the pipeline works; they do not validate the system for production use. See
[`LIMITATIONS.md`](LIMITATIONS.md).

Everything is on-premises by design. The target users are chemical plants subject to Russian
personal-data and critical-infrastructure law, where sending safety data to an external API is
not an option.

## Licensing, in short

Source code is [MIT](LICENSE). Data has separate provenance and terms — Russian regulatory
values (official documents, not subject to copyright under art. 1259(6) of the Russian Civil
Code), US federal agency material in the public domain (PubChem, NIOSH IDLH, ERG), and a
generated sheet form which is original work of this project. Full breakdown, including how to
anonymise the site registry before a public demo, is in [`DATA-LICENSE.md`](DATA-LICENSE.md).

## Contributing

The most valuable contribution is checking a regulatory value against the paper source — there
is a dedicated issue template for that. Working agreements and the project's non-negotiable
rule are in [`CONTRIBUTING.md`](CONTRIBUTING.md) (Russian).

Breaking the honesty contour — making the system emit a value without provenance, bypass
abstention, or convert units — is treated as a first-class vulnerability and is accepted as a
contribution rather than a complaint. See [`SECURITY.md`](SECURITY.md).
