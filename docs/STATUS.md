# STATUS

Session log. Commands and results only. Newest first.

Toolchain on the tech lead's machine: `uv` 0.12.19 (installed with `python3 -m pip install --user uv`,
binary at `~/Library/Python/3.9/bin/uv`), CPython 3.12.14 via `uv python install 3.12`.

---

## M5.2 with mechanical own-passage rule (V10) — 2026-10-01 — every scripted condition PASSES; ratings (human) outstanding

M5.2 not ticked: only `ratings.complete` and `ratings.supported` fail, and both are the tech lead's human ratings.
Provider `gemini`, model `gemini-3.5-flash-lite`, generated mode, 29 displayed paragraphs. Fixtures and ratings.json
untouched.

| Condition | Result |
|---|---|
| generated; e4 unverified / naked / advice / mismatched placeholders | PASS (0/0/0/0) |
| e8 risk recall | 14/14 PASS (tech lead's bar met) |
| e8 KAM recall | 3/3 PASS |
| e8 going concern correct | PASS |
| qa.passed >= 17 | PASS: 17/20 |
| ratings complete / supported >= 0.9 | FAIL: not rated (contradicted == 0 PASS) |

V10: list bullets (one per risk, in order of appearance) must each cite a passage no earlier in the report than the
previous bullet's. The section overview is the first passage, so only the first bullet may cite it; a later bullet citing
it is rejected and the violation goes back on the single retry (a retry never makes a topic worse). Relevance tests
(title words in the chunk, lexical rank of the chunk for the title) could not enforce this: the overview contains both
words of "Legal and regulatory" and ranks 2nd. Risk bullets now cite pages 55,56,56,57,57,58,58,59,59,60,60,61,61,62,
so "Legal and regulatory" cites its own page 62.

Misses (id | expected | top-8 PDF pages | answer):
v2 pages [7,8] "Growth Action Plan 2030" | 38,229,9,73,220,104,38,96 | validation_failed
v3 pages [11,12] "underlying sales","volume" | 12,11,101,11,85,84,35,102 | ok, cited page 11, missed both required terms
v4 pages [63,64] "Ice Cream" | 63,129,63,64,128,123,128,227 | validation_failed (passed in one earlier run; the model step varies)
Caveat on v1/v7: they pass by returning all 14 risk bullets; v1 asks which risks' level increased, and the level
(Increase / No change) is not in the indexed text, so the answer is a superset, not a filtered list.
The pass margin is exactly 17; v4 flips between runs, so a different run can land at 16 or 18. Three runs on this build:
risk 14/14 (before V10), 13/14, 14/14 (with V10); QA 13, 17, 17.

To finish M5.2: rate each displayed paragraph in fixtures/expected/ratings.json (ids = artefacts/commentary/company_a.json
"claims"), then `python scripts/gate.py M5.2`; replay: `finintel commentary company_a --replay
artifacts/commentary/company_a.json` must reproduce `output` byte for byte (RUN: byte-identical, offline, 5 s, same e4/e8/qa; 50,410 bytes of `output`).

| Command | Result |
|---|---|
| `make ci` | exit 0: 897 passed |
| `uv run python scripts/gate.py M5.2` | exit 1 only on ratings.complete and ratings.supported |

---

## M5.2 with supplemental facts (ADR-011, option A) — 2026-10-01 — scripted gate PASSES except ratings; tech lead's 14/14 risk bar MISSED (13/14)

M5.2 not ticked: ratings are human and not done, and the tech lead's stated bar (risk recall 14/14) is missed in this
run. Provider `gemini`, model `gemini-3.5-flash-lite`, generated mode, 27 displayed paragraphs. Fixtures and
ratings.json untouched.

| Condition | Result |
|---|---|
| generated; e4 unverified / naked / advice / mismatched placeholders | PASS (0/0/0/0) |
| e8 KAM recall 3/3, going concern correct | PASS |
| e8 risk recall | 13/14 = 0.93 (scripted bar >= 0.8 PASS; tech lead's bar 14/14 MISS) |
| qa.passed >= 17 | PASS: 17/20 |
| ratings complete / supported >= 0.9 | FAIL: human ratings not done (contradicted == 0 PASS) |

Built: finintel/facts (ADR-011): SupplementalFacts read by row label from table geometry (header alignment, block
period row, unit from header or printed suffix; no page given in advance; occurrences must agree within printed
rounding, else null + warning). Extracted on company_a, all matching the tech lead's labels and each with source pages:
basic EPS 2.30 (pp 141, 162), free cash flow 6,932 (pp 41, 43, 49), underlying operating profit 11,179 (p 47), Ice Cream
operating profit 571 (p 149), parent investment 88,035 (pp 132, 197). Reached the model only as `fact:` placeholders; the
numeric route returns a placeholder key and code renders it (no quote bypass). The meaning guard treats "underlying
operating profit" as a different measure from the reported item. 15 extractor tests + 6 placeholder tests; the full-report
test asserts the five values against fixtures/expected/company_a.qa.json.

Numeric QA now passes n1-n6 and t1-t3 (n4 EUR2.30; n5 EUR6.9bn, pp 41/43/49; n6 EUR11.2bn, p 47; t2 EUR571.0m, p 149;
t3 EUR88.0bn, pp 132/197). Note t2/t3 render with the generic money formatter (EUR571.0m, EUR88.0bn), which is rounded
display; the scored value is the exact fact.

Misses (id | expected | top-8 PDF pages | answer):
v2 pages [7,8] "Growth Action Plan 2030" | 38,229,9,73,220,104,38,96 | validation_failed
v3 pages [11,12] "underlying sales","volume" | 12,11,101,11,85,84,35,102 | validation_failed
v4 pages [63,64] "Ice Cream" | 63,129,63,64,128,123,128,227 | validation_failed (it passed in the previous run: the model
  step is not stable run to run)
Risk recall 13/14: all 14 risk bullets exist, but "Legal and regulatory" cites page 55 (the section's overview passage,
which lists risks and their levels), not its own page 62, so e8 correctly counts it missing. The earlier run had 14/14.
The cite-its-own-page rule is not enforced mechanically: the model may cite the overview chunk for any risk.

| Command | Result |
|---|---|
| `make ci` | exit 0: 896 passed |
| `uv run python scripts/gate.py M5.2` | exit 1 only on ratings.complete and ratings.supported |

---

## M5.2 with placeholder guard, code-built going concern, list routing — 2026-10-01 — GATE FAILED: qa 13/20

GATE FAILED at M5.2 (one condition set short). Provider `gemini`, model `gemini-3.5-flash-lite`, generated mode, 30
displayed paragraphs. Fixtures and ratings.json untouched. M5.2 unticked.

| Condition | Result |
|---|---|
| generated; e4 unverified / naked / advice | PASS (0/0/0) |
| e4 mismatched placeholders (new) | PASS (0) |
| e8 risk recall 14/14, KAM recall 3/3 | PASS |
| e8 going concern correct | PASS (code-built bullets at the two "Going concern" headings, PDF 123 and 145) |
| qa.passed >= 17 | FAIL: 13/20 (was 10) |
| ratings complete / supported | FAIL: human ratings not done (contradicted == 0 PASS) |

Built this round: V9 placeholder-meaning guard (each placeholder bound to a field; its own sentence must name the field;
the v3 sentence is rejected; audit counts mismatches; gate requires 0); going-concern bullets built by code from
passages headed exactly "Going concern" (pages found by heading, none named in code; no model); the model is told
not to write about going concern or KAMs (prompt commentary-3); list-shaped QA questions (principal risks, key audit
matters, going concern) are answered from the validated bullets by routing on the question's words.

Passed: a1 a2 a3 n1 n2 n3 t1 v1 v4 v5 v6 v7 v8. Misses (id | expected | top-8 PDF pages | answer):
n4 EPS 2.3 | pack route | insufficient_evidence
n5 free cash flow 6,932 | pack route | insufficient_evidence
n6 underlying operating profit 11,179 | pack route | insufficient_evidence
t2 Ice Cream operating profit 571 | pack route | insufficient_evidence
t3 parent investment 88,035 | pack route | insufficient_evidence
v2 pages [7,8], "Growth Action Plan 2030" | 38,229,9,73,220,104,38,96 | cited 9 and 96 (strategy text; pages 7-8 not retrieved): fails by rule
v3 pages [11,12], "underlying sales","volume" | 12,11,101,11,85,84,35,102 | cited 11: "...solid progress in 2024..." (no wrong figure now; missed the two required terms)

Blocker, not built: item 3 (extend the pack with EPS, FCF, underlying operating profit, Ice Cream operating profit,
parent investment). It changes the locked statement_pack schema (ADR + version), is M2-scale extraction, "from the
labelled pages" would hardcode the answer key's pages, and FCF/underlying are non-GAAP measures and Ice Cream is
segment data, not audited statement lines. Without it n4 n5 n6 t2 t3 cannot pass, so the ceiling is 15/20 against a
bar of 17 (13 now; v2 and v3 are the other two). Two options for the tech lead: (A) a separate typed
supplemental-facts record, outside the StatementPack, each fact with value, unit, period, page, raw_text, confidence,
`is_apm`, extracted generically by row label from table text (not by labelled page), placeholder-only; (B) extend the
StatementPack schema with an `is_apm` flag (ADR, version bump, golden labels updated by the tech lead). Either needs
a decision, and the accounting for APMs needs sign-off.

| Command | Result |
|---|---|
| `make ci` | exit 0: 876 passed |
| `uv run python scripts/gate.py M5.2` | exit 1 (qa 13/20, ratings) |

---

## M5.2 Gemini run with lists, floor, pack route — 2026-10-01 — GATE FAILED: qa 10/20, going concern flipped

GATE FAILED at M5.2. Provider `gemini`, model `gemini-3.5-flash-lite`, mode generated. Fixtures and ratings.json
untouched. M5.2 unticked. Two generated runs on this build (the first lost 9 QA answers to Gemini 503s; QA now re-asks
only unanswered questions after a cool-down, never answered ones).

| Condition | Run A (9 errors) | Run B (clean) |
|---|---|---|
| e4 unverified / naked / advice | 0/0/0 | 0/0/0 (27 displayed paragraphs) |
| e8 risk recall | 14/14 PASS | 14/14 PASS |
| e8 KAM recall | 3/3 PASS | 3/3 PASS |
| e8 going concern correct | True PASS | False FAIL |
| qa.passed >= 17 | 6 | 10 FAIL |
| ratings complete | not rated | not rated |

Going concern is not stable between runs: in run B the governance topic's model paragraphs were all rejected (pre-
validation: 2 fabricated quotes, 2 naked numbers across 5 calls), so only the three code-built KAM bullets remained
and no paragraph discussed going concern. It passed in run A because the model paragraphs survived.

Run B passed n1 n2 n3 v4 v6 v7 a1 a2 a3 t1. Misses (id | expected | top-8 PDF pages | answer):
n4 EPS 2.3 | pack route | insufficient_evidence (EPS is not a pack item)
n5 FCF 6,932 | pack route | insufficient_evidence (not a pack item)
n6 underlying op profit 11,179 | pack route | insufficient_evidence (not a pack item)
t2 Ice Cream 571 | pack route | insufficient_evidence (not a pack item)
t3 parent investment 88,035 | pack route | insufficient_evidence (not a pack item)
v1 [55,59,60,62] | 55,55,240,63,57,239,265,257 | insufficient_evidence by the evidence floor (coverage 0.63 < 0.68)
v5 [123] | 128,123,128,145,76,129,91,140 | insufficient_evidence by the evidence floor (coverage 0.59)
v2 [7,8] | 38,229,9,73,220,104,38,96 | ok, cited p9: Growth Action Plan strategy text (page 9, not 7-8)
v3 [11,12] | 12,11,101,11,85,84,35,102 | ok, cited p11: "Unilever made solid progress in EUR19.2bn ..." (a WRONG figure: a placeholder used for the
  wrong item; EUR19.2bn is current assets; also missed a must_mention term)
v8 [131] | 131,131,189,134,188,189,90,146 | ok, cited p131 (auditor testing satisfactory); missed must_mention "3230"

Arithmetic ceiling under the current rules: n4 n5 n6 t2 t3 cannot pass (figures not in the pack, quotes disallowed
on the numeric route) and v1 v5 are refused by the floor, so at most 13/20 can pass against a bar of 17.
Findings:
- v3 shows a displayed wrong number. The validators allow any known placeholder; they do not check that the placeholder
  means what the sentence says. This is the product's central risk ("does not lie about money") and is not mechanically
  caught. A guard is possible but not built: bind each placeholder to a label the sentence must carry, or require the
  model to name the item and verify it. Needs the tech lead's call.
- The evidence floor (0.68, calibrated on E3 only) refuses two answerable questions (v1, v5) and catches all three
  absent ones (a1 0.47, a2 0.57, a3 0.47). Moving it to 0.58 would pass both but is tuned to the QA labels; not done.
- LLM output varies run to run (going concern), so a single run is not a stable pass or fail.
- e8 recall of 14/14 and 3/3 is earned from the report's own text, not from the label file.

| Command | Result |
|---|---|
| `make ci` | exit 0: 872 passed |
| `uv run python scripts/gate.py M5.2` | exit 1 (going concern, qa 10/20, ratings) |

---

## M5.2 lists + floor + numeric route — 2026-10-01 — built; Gemini run NOT completed (503s), gate not re-run

M5.2 NOT passed and NOT re-measured: every attempt to run the new commentary against Gemini fell back to extractive
because Gemini returned HTTP 503 "high demand" on the real prompts (tiny prompts sometimes return 200). Fallback runs
are labelled extractive and do not count. Fixtures and ratings.json untouched.

Built for the tech lead's decision (change the commentary; bar unchanged):
- Chunker fix (M4.1 code, CHUNKER_VERSION 1.1.0): a key audit matter headed "(Parent company)" inside the auditor's
  report was classified company_statements and dropped from the index (PDF 132 had no chunks). It is now kept, so the
  third KAM exists. M4.1 gate 4/4 PASS (1,210 chunks), M4.2 gate PASS (hit@8 0.80).
- governance_and_directors: one code-built bullet per key audit matter (numbered sub-headings under the auditor's
  "Key audit matters" heading; title plus the first quotable sentence of its own section, cited at its own page),
  only if the auditor's report was retrieved. Works in extractive mode too: 3 bullets on company_a.
- strategic_risks: one model call over the principal-risks section (all chunks under the retrieved risks heading),
  one bullet per distinct risk, each citing its own passage; every bullet passes V1-V8; skipped for small-context
  providers (local Ollama) and sections under 3 chunks. Cap 20 (not 14: a generic cap, no label count).
- Numeric QA (questions with an `answer`): answered from the statement pack, no retrieval; the model returns a
  placeholder key only, code renders it. A figure the pack does not hold gets insufficient_evidence. Consequence:
  n4 (EPS), n5 (free cash flow), n6 (underlying profit), t2 (Ice Cream) and t3 (parent investment) cannot pass by
  construction, so QA is capped at 15/20 under this rule against a bar of 17. Needs the tech lead's decision.
- Evidence floor before any model call for narrative/absent QA: idf-weighted query-term coverage of the best chunk
  (`lexical.evidence_coverage`), COVERAGE_FLOOR 0.68, calibrated on the five E3 queries only (min 0.73, margin 0.05),
  not on QA. Measured on QA: a1 0.47, a2 0.57, a3 0.47 are refused; v1 0.63 and v5 0.59 (answerable) would also be
  refused. Dense cosine and BM25 did not separate absent from present questions (a1-a3 cosine 0.61-0.64, as high as
  real queries).
Decision I did not follow literally: "one bullet per principal risk in company_a.coverage.json". That file is the e8
answer key; generating from it would pass recall by construction. Lists come from the report's own structure and text.
Also: risk names (e.g. "Consumer preference") are not in the indexed chunk text, so recall depends on the model titling
each passage in words that overlap the labelled names.
Adapter: default `gemini-3.5-flash-lite` (3.1-flash-lite and the flash models 503 intermittently; 2.0/2.5 closed to new
users); 6 attempts with 10 s-linear backoff; errors now carry the HTTP status in the fallback reason.

| Command | Result |
|---|---|
| `make ci` | exit 0: 872 passed |
| `uv run python scripts/gate.py M4.1` / `M4.2` | PASS / PASS |
| `make eval-live COMPANY=company_a STAGE=commentary` (Gemini) | fell back to extractive: HTTP 503 after retries |

---

## M5.2 Gemini run — 2026-10-01 — GATE FAILED: qa 7/20, e8 0

GATE FAILED at M5.2. Provider `gemini`, model `gemini-3.1-flash-lite`, mode generated, no fallback. Fixtures and
ratings.json untouched. M5.2 unticked. Model choice: `gemini-2.0-flash` and `-2.5-flash` are closed to new users,
and `gemini-3.5/3.6/3.7/3.8-flash` returned 503 "high demand" on the real prompts, so the working lite model is the
default (override with GEMINI_MODEL). Adapter fixes: no `seed` (Gemini rejects it), 4 attempts with backoff on 5xx.

| Gate condition | Result |
|---|---|
| generated; e4 unverified / naked / advice | PASS (0/0/0 over 12 displayed paragraphs) |
| e8 risk recall (0/14), KAM recall (0/3), going concern | FAIL |
| qa.passed >= 17 | FAIL: 7/20 (local llama3.1 was 3/20) |
| ratings complete | FAIL (not rated) |

Pre-validation (5 calls): naked numbers 7, direction 1, unknown placeholders 0, schema 0, fabricated quotes 0.
Gemini follows the contract; the rejected paragraphs are mostly number discipline.

Questions that missed (id | expected | top-8 PDF pages | answer):
n1 [141] | 266,190,83,145,218,124,191,187 | validation_failed
n4 [141] | 162,9,162,15,82,193,223,110 | insufficient_evidence
n5 [43,49] | 15,9,43,15,16,165,49,44 | validation_failed
n6 [149] | 15,35,9,11,15,27,47,190 | validation_failed
v1 [55,59,60,62] | 55,55,240,63,57,239,265,257 | validation_failed
v2 [7,8] | 38,229,9,73,220,104,38,96 | ok, cited 9,10,96,229 (Growth Action Plan; not pages 7-8)
v3 [11,12] | 12,11,101,11,85,84,35,102 | ok, cited 11; failed a must_mention term
v4 [63,64] | 63,129,63,64,128,123,128,227 | validation_failed
v5 [123] | 128,123,128,145,76,129,91,140 | validation_failed
v8 [131] | 131,131,189,134,188,189,90,146 | validation_failed
a2 absent | 82,117,193,159,67,280,111,124 | validation_failed
t2 [35,149] | 35,16,149,11,244,79,190,35 | validation_failed
t3 [132] | 248,203,124,194,145,185,153,11 | validation_failed
Passed: n2, n3 (placeholders), v6, v7, a1, a3, t1.

Findings:
- Commentary coverage cannot reach 0.8 as built: each topic yields 1-2 short paragraphs (<= 90 words), so it
  cannot name 12 of 14 principal risks or 3 key audit matters. strategic_risks cited pages 54 and 290 and spoke
  generally. This is a design gap between the E8 labels and the commentary shape, not a model fault. Options for the
  tech lead: have strategic_risks and governance emit one bullet per risk or KAM (evidence-driven), or score E8 over
  the QA answers, or lower the bar.
- Most remaining validation_failed are naked numbers around figures the model restates from quotes outside quotation
  marks; V5 is strict by design.
- Retrieval: expected pages are missing from the top 8 for n1, n4, n6 (statement pages 141/149 are excluded from the
  narrative index by design) and v2 (page 9, not 7-8).

---

## M5.2 rerun — 2026-10-01 — GATE FAILED again: qa 3/20 (local llama3.1, prompt commentary-2)

GATE FAILED at M5.2. Same conditions fail: e8 risk 0/14, kam 0/3, going concern, qa.passed 3/20, ratings not done.
Provider `local`, mode generated. Fixtures and ratings.json untouched. M5.2 unticked.
Change tested: V4 now rejects currency or unit text beside a placeholder, and prompt commentary-2 says so. The
doubled units ("EUR EUR60.8bn", "bnbn") are gone from displayed answers (n5 now "EUR6.1bn"). Passed: v6, v7, a1
(from 2 to 3 passes). Displayed answers that are still wrong: n5 "Free cash flow ... EUR6.1bn" (expected 6,932m), a3
(a quoted "No dividends are payable" answer to an absent question, should be insufficient_evidence).
Pre-validation (5 calls): unknown placeholders 9, naked numbers 4, schema 2, fabricated quote 1, no citation 1.
Most calls end validation_failed: the 8B model under a 4,096-token context does not follow the placeholder and
quote contract. More prompt or validator tuning will not close a 3/20 -> 17/20 gap with this model.
Needs a decision from the tech lead: a larger local context or model, or a hosted provider (FININTEL_PROVIDER).

---

## M5.2 — 2026-10-01 — GATE FAILED: live local run (llama3.1) is generated but too weak

GATE FAILED at M5.2. Run is a real model run, labelled `local` (Ollama, `llama3.1`, OpenAI-compatible
`/v1/chat/completions`, mode=generated, no fallback). Not an extractive stub. M5.2 unticked. Fixtures untouched,
ratings.json untouched (still not_rated).

| Gate condition | Result |
|---|---|
| commentary.mode == 'generated' | PASS |
| e4 displayed unverified citations / naked numbers / advice | PASS (0 / 0 / 0, over 4 displayed paragraphs) |
| e8.risk_recall >= 0.8 | FAIL: 0/14 |
| e8.kam_recall >= 0.8 | FAIL: 0/3 |
| e8.going_concern_correct | FAIL (no governance paragraph survived) |
| qa.total == 20 / qa.passed >= 17 | total PASS; passed 2/20 FAIL |
| ratings.complete / supported >= 0.9 | FAIL: human ratings not done (contradicted == 0 is vacuous) |

Commentary: revenue_drivers, governance_and_directors, liquidity_and_capital = validation_failed (0 paragraphs);
strategic_risks 1 paragraph; executive_summary 3 bullets. Pre-validation (5 calls): unknown placeholders 5, naked
numbers 3, schema 2, fabricated/out-of-set quote 1, no citation 1. Validators held: nothing unverified shown.

Questions that missed (id | expected pages | top-8 PDF pages retrieved | answer):
n2 [141] | 190,15,35,47,15,9,15,19 | validation_failed
n3 [141] | 15,35,191,190,15,49,19,16 | validation_failed
n4 [141] | 162,9,162,15,82,193,223,110 | validation_failed
n5 [43,49] | 15,9,43,15,16,165,49,44 | ok: "Free cash flow for 2024 was EUR EUR6.1bnbn." (wrong figure)
n6 [149] | 15,35,9,11,15,27,47,190 | validation_failed
v1 [55,59,60,62] | 55,55,240,63,57,239,265,257 | validation_failed
v2 [7,8] | 38,229,9,73,220,104,38,96 | validation_failed
v3 [11,12] | 12,11,101,11,85,84,35,102 | validation_failed
v4 [63,64] | 63,129,63,64,128,123,128,227 | validation_failed
v5 [123] | 128,123,128,145,76,129,91,140 | ok: going concern basis answer (quotes/must_mention not satisfied)
v6 [124,130,131,132] | 129,124,136,90,91,92,283,68 | validation_failed
v8 [131] | 131,131,189,134,188,189,90,146 | validation_failed
a1 absent | 83,219,218,213,293,60,61,83 | validation_failed (should be insufficient_evidence)
a2 absent | 82,117,193,159,67,280,111,124 | validation_failed
a3 absent | 81,193,82,193,76,15,223,217 | validation_failed
t1 [141] | 47,47,47,15,9,15,148,149 | validation_failed
t2 [35,149] | 35,16,149,11,244,79,190,35 | ok: "Ice Cream operating profit 2024 was EUR EUR9.4bn." (the group figure: the trap)
t3 [132] | 248,203,124,194,145,185,153,11 | ok: "investment in subsidiaries is EUR EUR6.1bnbn ... group turnover EUR EUR60.8bnbn" (wrong)
Passed: n1, v7.

Findings:
- Retrieval and the model both contribute. An expected page is NOT in the top 8 for n2, n3, n4, n6, v2 (page 9
  only, not 7-8) and n6; it IS in the top 8 for n5, v1, v3, v4, v5, v6, v8, t1, t2, t3-adjacent pages and the model
  still failed or answered wrongly on most of them. Under the 900-token local evidence budget the model sees only
  2-5 pages per question.
- Ollama's OpenAI-compatible endpoint has a fixed 4,096-token context (measured: a 6.5k-token prompt lost its first
  lines, i.e. the rules). Prompts are sized to fit (evidence 900 tokens, prompt guard 10,500 chars, shrink-to-fit,
  retry skipped when too long). This is the main quality limiter for the local run.
- Displayed answers contained semantic errors the mechanical validators cannot catch: n5, t2, t3 each used an
  existing placeholder for the wrong concept (e.g. group operating profit for Ice Cream; figures the question did
  not ask for). Validators check numbers are placeholders or quotes, not that the placeholder means what the claim says.
- The model also writes its own currency symbol and "bn" around a placeholder, printing "EUR EUR60.8bn" and "bnbn".
  V5 does not flag these (no digits outside the placeholder). Candidate follow-up: reject unit text adjacent to a
  placeholder. Not changed here.
Local provider hardening added: retry once on 5xx/timeout (new seed), 180 s timeout, per-question failure no
longer aborts the run, evidence shrink-to-fit, prompt_too_long guard, per-question answers recorded in report.qa.

| Command | Result |
|---|---|
| `make eval-live COMPANY=company_a STAGE=commentary` | exit 0, mode=generated provider=local |
| `uv run python scripts/gate.py M5.2` | exit 1 |
| `make ci` | exit 0: 861 passed |

---

## M5.2 (offline parts) — 2026-10-01 — NOT green: no live run, ratings not done

M5.2 offline parts built and tested. Gate NOT met: it needs a live model run, which needs `ANTHROPIC_API_KEY`
(`.env` sets only `ANTHROPIC_BASE_URL`), and the tech lead's `ratings.json` (status `not_rated`). M5.2 unticked.
`make ci`: 854 passed. `pytest tests/commentary`: 87 passed. With the key unset the run exits 0 and is labelled
extractive, as the gate requires; `gate.py M5.2` correctly fails on `commentary.mode == 'generated'` and the
missing e8/qa/ratings sections, so an extractive run cannot pass the gate by satisfying e4 alone.

| Command | Result |
|---|---|
| `make ci` | exit 0: 854 passed, 5 deselected |
| `uv run pytest tests/commentary -q` | 87 passed |
| `make eval-live COMPANY=company_a STAGE=commentary` (no key) | exit 0, mode=extractive, 12 paragraphs, e4 all zero |
| `uv run python scripts/gate.py M5.2` | exit 1 (mode, e8, qa, ratings) |
| `check_scope.py M5.2 --base bebf644` | only the tech lead's uncommitted fixtures/expected files (G2/G3) |

Built: prompts (`commentary-1`; the model sees chunk ids and text, never pages), topic-scoped ground truth, context
expansion (+-1 same-section neighbours, 3,500-token budget), topic and summary calls with validate -> retry once ->
drop (retry never makes a topic worse), extractive mode, numbers snapshot, record/replay providers (replay is
byte-identical), Anthropic adapter (httpx, MockTransport-tested only), E4 audit of displayed output re-derived from
chunk text, E8 coverage, 20-question scoring, ratings arithmetic, `finintel commentary` and `make eval-live`.
Not done: topic calls are sequential, not parallel; no "linked footnotes" in context expansion; the adapter has
never run against the live API.

The tech lead's label files (coverage, qa, ratings) arrived mid-session with a shape different from EVAL 3.4/3.6:
`kind`/`q`/`pages`/`must_mention`, no aliases. Scorers follow the files, not the doc. Decisions to confirm:
- Numeric answers: right when a displayed paragraph's `item:` placeholder has the labelled pack value in the
  question's unit, or quotes (verified) a number in `accept`. The rounded rendering is never compared.
  n3-n6 and t2 (net profit, EPS, free cash flow, underlying and Ice Cream operating profit) are not StatementPack
  items beyond net income, so they can pass only through a verbatim quote.
- Trap questions also fail when `not_answer` is stated by either route.
- Narrative: `must_mention` means ALL terms; `pages` means any cited page (exact, not +-2).
- Coverage: an item is covered when >= 60% of its name's content words (parentheticals dropped, plural-s stripped)
  appear in a displayed paragraph citing within +-2 pages of any listed page. Going concern: must be discussed on or
  near the listed pages; "material uncertainty" outside quotes counts as a claim unless negated ("no", "not",
  "without"), derived from the label's conclusion because no `must_not_claim` is given.
- Ratings: `{"status": "rated", "items": [{"id": "<topic>:<n>", "rating": "supported|unsupported|contradicted"}]}`,
  ids from the artefact's `claims`; complete only when every displayed paragraph is rated once.
Other: the evidence-floor is meaningless under the RRF-order reranker (scores are positions), so retrieval never
declares insufficient_evidence for company_a; `qa.absent` questions rely on the model's own status.

To finish M5.2: set `ANTHROPIC_API_KEY` in `.env`, run `make eval-live COMPANY=company_a STAGE=commentary`, rate the
displayed paragraphs in `ratings.json`, then `python scripts/gate.py M5.2` and
`finintel commentary company_a --replay artifacts/commentary/company_a.json` (must reproduce `output`).

---

## M5.1 — 2026-10-01 — green, except G3 on the tech lead's uncommitted fixture edit

M5.1 green. Schemas, renderer and validators V1-V8 built; T1-T18 pass on scripted outputs (network blocked).
`pytest tests/commentary -q`: 56 passed. `make ci`: 823 passed, 5 deselected. No LLM, no provider code.
`check_scope.py M5.1 --base m4.1` flags only `fixtures/expected/company_a.retrieval.json` (G2/G3): the tech
lead's relabel is still uncommitted. Claude does not commit expected files. G1-G6 therefore not ticked.

| Command | Result |
|---|---|
| `uv run pytest tests/commentary -q` | 56 passed (T1-T18 in test_hallucination.py; render 18; quotes/numbers/schemas) |
| `make ci` | exit 0: 823 passed, 5 deselected |
| `uv run python scripts/gen_contracts.py --check` (inside ci) | up to date |

Built: schemas/citation.schema.json, schemas/commentary.schema.json (generated finintel/contracts/citation.py,
commentary.py; the commentary schema embeds the citation def, a test keeps the two identical);
finintel/commentary/render (exact half-up rendering; GROUND_TRUTH builder keyed `kind:id:period`);
finintel/commentary/validators (quote location with an offset map, citation builder with page and bbox from the
char->page map, V5 naked numbers incl. spelled-out, V6 advice, V7 direction, V1/V2/V4/V8 orchestration,
`feedback` and `finalize` for the M5.2 retry-then-drop loop).

Design points to review:
- Ratio and item placeholders carry the direction of the change into their period (None for the earliest
  period). A direction word beside a placeholder with no direction is a violation (RAG V7).
- V7 pairs each direction word with the nearest placeholder in its sentence, so mixed sentences can be valid.
- Text inside double quotation marks is exempt from V5/V6/V7 only when it is a substring of a verified quote
  (T12). So the model can quote an injected sentence verbatim; it is then shown as a quotation, not asserted (T7).
- Strict by design: "one" (not "one of"), "half" and any digit outside a period label, a cited note number or a
  quote are violations; "growth", "up", "down" are not direction words.
- RAG T13 calls the direction mismatch "soft"; V7 says hard. Implemented as hard (retry, then drop).
- The summary schema requires 3-5 bullets; it validates through the same V1-V8, with evidence limited to chunks
  cited by validated paragraphs (`summary_evidence`).
Not built (M5.2): prompts, provider adapter, topic and summary calls, retry loop, extractive mode, persistence.

---

## M4.2 — 2026-10-01 — gate PASS at the bar (0.80); strategy query still misses

M4.2 gate `e3.hit_at_8 >= 0.8` passes: 4/5 = 0.80 with local BAAI/bge-m3 + heading-aware hybrid. Exactly at the
bar, with no margin. Labels not edited. Re-indexed from the PDF; no page inserted by hand. Sign-off "top 8 for
principal risks on-topic" is the tech lead's and is open, so M4.2 is not ticked in MILESTONES.

Models: embedding BAAI/bge-m3 (1024-d, mps), reranker none (RRF order). The bge reranker is a separate ~2 GB
download, not in the bge-m3 one, and RRF met the bar; evidence-floor scores are positions, not relevance, in this mode.

| Query | Expected PDF | Result |
|---|---|---|
| principal risks | 54-62 | HIT |
| strategy | 7-8 | MISS |
| CEO on performance | 11-12 | HIT |
| viability statement | 63-64 | HIT |
| going concern | 123, 145 | HIT |

Strategy miss (top 8 PDF pages, dense cosine / BM25 / dense rank / BM25 rank):
38 .670/4.12/2/20; 229 .667/4.35/4/17; 9 .631/4.75/18/8; 73 .612/4.75/36/7; 220 .631/4.04/20/21;
104 .615/4.41/30/15; 38 .608/4.53/40/14; 96 .634/3.39/13/49.
The PDF 7-8 chunks ("Our Strategy: GAP 2030" infographic fragments) rank dense 56-920 (cosine 0.25-0.60) and BM25
10-34 (best 4.58, on page 8 "scaled artificial intelligence"); RRF 0.0106-0.0143 vs 0.0229+ for the top 8. The
heading match did not outrank them: the section's text is short infographic labels with little query vocabulary.
Not tuned further: raising the heading weight to chase this one query would overfit a 5-query set.

| Command | Result |
|---|---|
| `make eval-e3 COMPANY=company_a` (memory backend, bge-m3) | 4/5 = 0.80 |
| `uv run finintel eval-e3 company_a --backend postgres` | 4/5 = 0.80, same pages (Postgres FTS is `ts_rank_cd`, not BM25) |
| `uv run python scripts/gate.py M4.2` | exit 0, PASS e3.hit_at_8 >= 0.8 |
| `make migrate` / `make test-db` | 002 applied; 5 passed |
| `make ci` | exit 0: 767 passed, 5 deselected |

Built: migration 002 (HNSW for bge-m3; heading-weighted `tsv` via IMMUTABLE `heading_text`); finintel/retrieval/lexical.py
(BM25F-style, heading weight 3, stopwords); local_models.py (BgeM3Embedder, MemoEmbedder disk memo); `--embedder`
flag (bge-m3 default, fake for tests); optional dependency extra `local` (sentence-transformers). First run
downloaded the model to ~/.cache/huggingface (4.3 GB).
Open: scope check flags the tech lead's uncommitted relabel of fixtures/expected/company_a.retrieval.json (G2/G3).

---

## M4.2 — 2026-10-01 — GATE FAILED: e3.hit_at_8 = 0.60 (3/5) after relabelling

GATE FAILED at M4.2. `e3.hit_at_8 >= 0.8` not met: 3/5, on the tech lead's relabelled file (PDF viewer pages; not edited).
Models: fake-hash-bow-v1 / fake-overlap-v1 (offline stand-ins). M4.2 unticked; M5 does not start.

Reader bug found and fixed (mine, not the fixture): the basis check matched "printed" inside "Not printed footer
numbers" and added the folio offset a second time (first rerun 1/5 with wrong expected pages 57-65 etc.). Basis
naming PDF/viewer pages is now used as-is; test added.

| Query | Expected PDF pages | Result |
|---|---|---|
| principal risks | 54-62 | HIT |
| strategy | 7-8 | MISS: got 63, 55-56, 177, 228, 44, 229, 278, 53 |
| CEO on performance | 11-12 | MISS: got 35, 80, 101, 172, 275, 85, 73, 74 |
| viability statement | 63-64 | HIT |
| going concern | 123, 145 | HIT |

The two misses are on labels that point at the right content (PDF 7-8 "Our Strategy: GAP 2030", 11-12 CEO statement)
and are retrieval misses with stand-in models; the retrieved pages are risk, governance and ESRS text.
Next: real embedder and reranker (Voyage needs a key; local bge-m3 needs a model download), then rerun.

| Command | Result |
|---|---|
| `make eval-e3 COMPANY=company_a` | 3/5 = 0.60 |
| `uv run python scripts/gate.py M4.2` | exit 1 (FAIL e3.hit_at_8 >= 0.8) |

---

## M4.2 (partial) — 2026-10-01 — NOT green: E3 gate blocked on labels

M4.2 partial. Postgres 17 + pgvector index built and tested; migrate gate passes. `make eval-e3` and the
`e3.hit_at_8` gate NOT run: `fixtures/expected/company_a.retrieval.json` is missing (format in docs/EVAL.md 3.3).
M4.2 stays unticked; M5 does not start. Sign-off "top 8 for principal risks on-topic" also pending.

| Command | Result |
|---|---|
| `docker compose up -d db && make migrate` | exit 0: `applied: 001_narrative_index.sql`; second run `nothing (up to date)` |
| `make test-db` | 5 passed against real Postgres (document-filtered dense/lexical, tables excluded, idempotent store, Postgres and in-memory backends agree) |
| `make ci` | exit 0: **758 passed, 5 deselected** (the 5 are `network`-marked DB tests) |
| `uv run python scripts/check_scope.py M4.2 --base m4.1` | exit 0 |

Built: docker-compose.yml (pgvector/pgvector:pg17, loopback only); migrations/001 (documents, chunks with generated
`tsv` + GIN, chunk_embeddings vector(1024), partial HNSW for the fake model); finintel/db (migrate, store,
PostgresIndex); finintel/retrieval (query sets by document_type, RRF, rerank, prior, diversity, floor).
pytest now runs `-m "not network"` by default; DB tests are `network`-marked and run via `make test-db`.
Not built: Voyage and local bge-m3 embedders (each needs its own HNSW migration), real reranker, eval-e3,
context expansion, floor calibration. NHS priors cannot name performance/accountability report (taxonomy gap, M8.1).

---

## M4.1 — 2026-10-01 — green (heading_path sign-off pending)

M4.1 green. company_a: 1,208 chunks, every one with `page_start`; 0 chunks in primary or company statements;
0 on excluded statement pages; 0 prose lines overlapping an independent table region (978 prose chunks).
No database. Next M4.2 (needs Docker/Postgres and `fixtures/expected/company_a.retrieval.json` from the tech lead).

| Command | Result |
|---|---|
| `make ci` | exit 0: **749 passed, 0 skipped** |
| `uv run python scripts/gate.py M4.1` | exit 0, 4/4 PASS |
| `uv run python scripts/check_scope.py M4.1 --base m3` | exit 0 (ruled_tables.py amendment in MILESTONES) |

Caveat: the independent table check unions the density detector with the same PyMuPDF ruled-table finder
production uses, so it is partly a wiring check, not a fully independent oracle.
Open: tech-lead sign-off "10 random chunks have correct heading_path values".

---

## M3 — 2026-10-01 — green

M3 green. ROCE 0.172426443613 (FY2024) and 0.188527599065 (FY2023) match the hand calculator at 1e-9.
Operating margin 0.154704 / 0.163714, current ratio 0.760640 / 0.761560. Debt-to-equity null,
`missing_input` (total_debt is null). unit_scale millions, EUR. Next M4.1.

| Command | Result |
|---|---|
| `make ci` | exit 0: **688 passed, 0 skipped** |
| `make eval-e2 COMPANY=company_a` | 8/8 cells expected, matched from the labelled pack AND from the pipeline's pack |
| `uv run python scripts/gate.py M3` | exit 0 (`e2.matched == e2.expected`) |
| `uv run python scripts/check_scope.py M3 --base m2.5` | exit 0 (with the amendment in MILESTONES) |

What shipped (finintel/ratios/engine.py, schemas/ratio_pack.schema.json, generated contract):
- The four locked ratios from the StatementPack only; exact Decimal division, converted once to float.
  pandas was not needed for four quotients.
- A null input gives `value: null`, `reason: "missing_input"` (CLAUDE.md wording) and names the input.
  A zero denominator gives `division_by_zero`. Negative equity or capital employed: the value is shown with
  `negative_denominator` beside it (ADR-008), plus a pack warning.
- `applicability` is separate: bank `not_applicable` (all four); unclassified balance sheet makes the current
  ratio `not_applicable`; `other` withholds the rest; NHS withholds all but the current ratio until OQ-5 is
  decided. A hidden-by-applicability ratio shows no number even if its inputs exist.
- A v1.0.0 pack has no document profile: treated as corporate, its own nulls decide. Stated in the docstring.
- Inputs carry item, value, page and badges (`derived`, `manual`, `manual_unanchored`). `total_debt` on
  a derived pack shows `derived` and no page.
- Changes: margin and ROCE in percentage points, multiples absolute, items absolute and percent; a
  null never turns into a number and a zero base gives a null percent. Periods sorted latest first.
- `statement_pack_sha` is the SHA-256 of the canonical pack JSON, so stale ratios are detectable.
- Drift test reads the formula strings out of CLAUDE.md and compares them with the code.
- Property test: multiplying every input by 1,000 changes no ratio, flag or reason (300 examples).

Notes:
- Unilever's FY2022 period (income statement only) gets ratios with missing balance-sheet inputs. Honest,
  but a UI decision for M7: show a prior-year column only when it has inputs.
- Tag `m3-done` (the web-directory guard, G5) is the tech lead's to create.
- Still pending from earlier: Azure key (M2.5 gate) and ADR-010 review of the six M2.3 specs.

---

## M2.5 — 2026-10-01 — BUILT, gate BLOCKED on an Azure DI key

M2.5 code complete and green offline. The gate command cannot pass honestly: no Azure key, so no real
response exists. Not advancing to M2.6/M3 claims; M3 does not depend on Azure and can proceed.

| Command | Result |
|---|---|
| `make ci` | exit 0: **656 passed, 0 skipped** |
| `make eval-e1 COMPANY=company_a ENGINES=all` (no key) | 22/22 matched, 0 silent wrong, Azure `engine_skipped: no credentials`, `reduced_verification` raised |
| `uv run python scripts/gate.py M2.5` | **exit 1: `FAIL azure.ran == True`** (by design: a skipped engine must not look like a pass) |
| `uv run python scripts/check_scope.py M2.5 --base m2.4` | exit 0 (with the amendment in MILESTONES) |

Built (tested on an Azure-shaped stand-in, tests/extract/fake_azure.py; NOT a recorded vendor response):
- `normalise_layout`: Azure layout JSON (inches, per-cell bounding regions) to ParsedTables in PDF points.
- Anchoring for non-text-layer engines: a figure the engine reports but the page does not print at that
  spot is an `unanchored_candidate` and is dropped. Verified: a "corrected" 12,600 never appears.
  Characters, row, column and period always come from the text layer (`row_source: text_layer`).
- Family voting: two families on the same cell x1.00 (else x0.90), engine `reconciled`; a cross-engine
  difference is resolved only if exactly one candidate passes every applicable arithmetic check (capped
  0.85), else null + `parser_disagreement`. Review items listed in the report.
- Azure called on the statement pages only (OQ-7 option B, about $0.08 a report), raw response cached;
  no key or a vendor failure gives `engine_skipped` and the local path unchanged.
- Tie-break tests: resolved by arithmetic (revenue) and unresolved when no check applies (cash).

Honest limits:
- Real Azure behaviour is unverified. Real layouts may split cells, merge rows or round coordinates in
  ways the stand-in does not; the anchoring rule is the safety net, but E1 on real output is the test.
- Because row/column/period are always text-layer derived, cross-family disagreement can only arise from
  which cells survive anchoring, so the second family mostly adds corroboration (x1.00) and a tripwire.
- tau calibration: note added to EXTRACTION 5.3 saying unchanged and pending real two-family evidence.

Needed from the tech lead to close M2.5: set `AZURE_DI_ENDPOINT` and `AZURE_DI_KEY` in `.env`, then
`make eval-e1 COMPANY=company_a ENGINES=all && python scripts/gate.py M2.5`. One disputed-cell sign-off
also remains (MILESTONES). Also pending from M2.3: ADR-010 review of the six new synthetic specs.

---

## M2.4 — 2026-09-30 — green

M2.4 green. E1 company_a: 22/22 matched (20 figures + 2 explicit `total_debt` nulls), silent_wrong 0,
unit_errors 0, published_llm_pointer 0. `total_debt` null with a specific warning. Next M2.5.

| Command | Result |
|---|---|
| `make ci` | exit 0: **646 passed, 0 skipped** |
| `make eval-e1 COMPANY=company_a ENGINES=local` | labelled 22, matched 22, honest_null 0, silent_wrong 0, unit_errors 0 |
| `uv run python scripts/gate.py M2.4` | exit 0 (4/4); M2.1-M2.3 gates still exit 0 |
| `uv run python scripts/check_scope.py M2.4 --base m2.3` | exit 0 (with the amendment in MILESTONES) |
| `uv run finintel extract company_b` | bank: every corporate item an explicit null, bank_layout + unclassified_balance_sheet warnings |

Label change (tech lead, 2026-09-30, commit c3418ee, CHANGELOG entry): company_a `total_debt` and
debt_to_equity are null under the strict rule. Unilever's face "Financial liabilities" includes derivatives
(594) and other financial liabilities (804), so it is not interest-bearing borrowings + leases.

What the pipeline does (finintel/extract.py): ingest, text layer, locate, both text-layer engines,
headers, alias-map mapping, arithmetic checks, publish-or-null.
- Confidence: base (exact .95, regex .90, structural .85) x 0.90 (one engine family), +0.05 if a check
  passes, -0.30 if one fails (failure dominates), cap 0.99, publish at >= 0.80. Unilever: revenue 0.855,
  operating profit 0.905, unlabelled current-assets subtotal 0.815 (only because its section sum passes).
- Engines that read different cells give null + `parser_disagreement` (tested with a perturbed engine).
  No tie-break in M2.4.
- Liabilities are stored positive; equity keeps its sign.
- `total_debt`: derived sum of four printed lines (engine derived, derived_from); borrowings only +
  `lease_not_separately_presented`; a found-but-null component makes it null; absent components are zero
  only when their section subtotal verified (`assumed_zero`); a face "Financial liabilities" line with no
  borrowings makes it null.
- LLM pointer: port, digit masking, schema (no numeric field) and row validation, FakeProvider. Suggestions
  are review items at 0.70 and never change the pack (byte-equal test). NOT built: a live Anthropic adapter
  (no key; the step records "skipped: no provider configured").

Decisions and findings:
- Ambiguous documents ("other", e.g. a statement with no revenue row) use the corporate alias map, since
  values stay anchored and checked; ratios are withheld in M3. Bank/NHS need their maps (M8.1) and list
  every required item as an explicit null meanwhile.
- The rounding tolerance (0.5 x n x unit) means a subtotal off by 1 on a 4-figure sum still passes. That is
  the documented EXTRACTION 5.2 rule; it is not tightened.
- A memo line between two chain anchors (an "Adjusted operating profit" row between revenue and operating
  profit) makes the chain check fail and both figures null: cautious, tested, and documented.
- Import cycle fixed: cached text-layer loader moved to finintel/parse/cached.py.
- Golden excerpt (OQ-10 = A): tests/golden/company_a/excerpt.pdf, 99 KB; regenerate with
  `python scripts/make_golden_excerpt.py company_a 141 143 195 197`.

Not yet done / carried to M2.5:
- Azure DI normalisation and cross-family voting; tau calibration (EVAL 6.1); `reduced_verification` is
  always raised until then.
- company_name is null (not confidently read from the statements).
- Pending from M2.3: tech-lead ADR-010 review of the six new synthetic specs.

---

## M2.3 — 2026-09-29 — green

M2.3 green. company_a: EUR x 1,000,000; FY2024 ends 2024-12-31, FY2023 ends 2023-12-31 (both equal
the labels), on both engines. Lloyds: GBP £m, same dates. Next M2.4 (blocked on the label update below).

| Command | Result |
|---|---|
| `make ci` | exit 0: **599 passed, 0 skipped** |
| `uv run python scripts/gate.py M2.3` | exit 0: status ok; EUR x 1000000; FY2024, FY2023 dates match; FY2022 printed, not labelled |
| `uv run python scripts/gate.py M2.1` / `M2.2` | exit 0 (7/7; 20/20 per engine) |
| `uv run pytest tests/tables/test_headers.py` | 12 specs x 2 engines: status, currency, scale, period ids, end dates, restatement, usable columns |
| `uv run pytest tests/tables/test_header_rules.py` | every SCHEMA 7 token; date rules below |

Rules as implemented (SCHEMA 7-8):
- One distinct unit token per statement (header band or title block); none or two block with
  `needs_unit_confirmation`; income statement and balance sheet must agree. "$" alone blocks with
  `currency_ambiguous` unless the report states a US dollar presentation currency.
- Day and month from the title block, year from the column. "Year ended 31 March 2025" also dates
  the 2024 column. "52 weeks ended", "period ended" and "as at 29 March 2025" never date a
  comparative (a 52/53-week year end shifts by days): that end date stays null unless printed.
- Year headers centred over a column group apply to the whole group; a phrase right-aligned with one
  column is that column's own ("Restated").
- Columnar income statements: one Total/Statutory column per period, or the period's figures stay
  null (`period_ambiguous`). Company columns are excluded with their reason; only Group feeds v1.

Bugs found by the new specs, now tested:
- "£000" parsed as the number 0: a unit row would have become an unlabelled row worth 0.
  Currency + "000"/"'000" is a unit, never a figure.
- A subtitle with a year ("For the year ended 30 June 2025") was swallowed into the header band, and
  a sub-header row ("Restated") cut the band short. Header rows are now found by position: rows
  above the first figure that sit over the figure columns.
- Sparse note references (one or two rows) are invisible to text-strategy grids and were merged into
  labels. When the engine finds no note column but a "Note(s)" header is printed, references under
  it are read from the text layer.

Pending (tech lead): ADR-010 review of the six new M2.3 spec files and the header expectations
added to the older six. Committed so the work is safe; amend if any figure is wrong.

Blocking M2.4 (tech lead): `fixtures/expected/company_a.json` and `company_a.ratios.json` still carry
the pre-decision `total_debt` (all financial liabilities, 32,053 / 29,622) and D/E 1.4211 / 1.4266.
Under the strict rule decided on 2026-09-29 they should expect `total_debt` null (with a warning) and
D/E null with `reason: missing_input`. Code never edits expected files.

---

## M2.2 — 2026-09-29 — green

M2.2 green. company_a: 20/20 labelled cells found by pdfplumber AND by PyMuPDF, each on its labelled
page, in a value column. Both engines produce identical rows on both goldens. Next M2.3.

| Command | Result |
|---|---|
| `make ci` | exit 0: **488 passed, 0 skipped** |
| `uv run python scripts/gate.py M2.2` | exit 0: pdfplumber 20/20, pymupdf_tables 20/20 |
| `uv run python scripts/gate.py M2.1` | exit 0 (still 7/7) |
| `uv run pytest tests/tables` | grammar, engines, 6 specs x 2 statements x 2 engines, goldens |
| `uv run python scripts/check_scope.py M2.2 --base m2.1` | exit 0 (with the amendment in MILESTONES) |

Tables on the goldens (both engines): Unilever IS p.141 19 rows, columns Notes | EUR m 2024 | 2023 | 2022;
BS p.143 43 rows; Lloyds IS p.216 31 rows (EPS "6.3p" recorded unparsed), BS p.218 44 rows.

What real reports taught this milestone (each is now a test):
- **Engines truncate hanging brackets.** Both grids cut ")" off right-column figures ("(493" for
  "(493)"). Per ADR-001, characters now come from the text layer: the engine's cell box says where,
  the printed words centred in it say what. The engine's own text is kept as `engine_text`.
- **Superscripts split rows.** Unilever's "(a)" footnote marker (4.55 pt) formed its own row and a
  figure row lost its values. Row grouping now attaches undersized glyphs to the row they overlap.
- **Prose fragments look like figures.** PyMuPDF read "d 31 Dece" from the subtitle; the printed
  "31" under it became a "figure". A cell whose edges cut through other words is never a figure.
- **Footnote prose merges columns.** Only figure-like cells (numbers, dashes, note references,
  years) define columns, and columns are measured on printed ink, not engine boxes.
- **Unheaded note columns.** Found by the EXTRACTION section 3 reference pattern (notes_column spec).

Proposed EXTRACTION section 3 amendment (the tech lead owns that document): the note-reference
pattern has no letter suffix, but Unilever prints "4B", "15C", "17A". The "Notes" header caught them
here; code also treats any letter-suffixed reference as a note (it can never be a value).

Carried into M2.3:
- Value-column headers as printed: Unilever "€ million 2024"; Lloyds "2024 £m". Three periods on
  both income statements (2024, 2023, 2022); labels cover two.

---

## M2.1 — 2026-09-29 — green

M2.1 green. company_a IS p.141 (printed 138), BS p.143 (printed 140): equal to the labels, folios too.
Company pages 195-197 detected, none selected. company_b: bank, balance sheet unclassified. Next M2.2.

| Command | Result |
|---|---|
| `make ci` | exit 0: **330 passed** |
| `uv run python scripts/gate.py M2.1` | exit 0, 7/7 PASS |
| `uv run finintel locate company_a --json` | IS [141] labels ['138']; BS [143] labels ['140']; corporate; classified |
| `uv run finintel locate company_b --json` | exit 0; `document_type: bank`, `balance_sheet_classified: false`; parent company BS p.307 rejected |
| `uv run pytest tests/locate/test_synthetic_specs.py tests/locate/test_goldens.py` | 11 passed (4 specs, 4 golden checks) |
| `uv run python scripts/check_scope.py M2.1 --base m1` | exit 0 (with the amendment below) |
| locate on a cached text layer | 0.4-0.5 s per report |

Decisions recorded:
- `total_debt` (tech lead, 2026-09-29): **strict**. A face line "Financial liabilities" that includes
  derivatives and other financial liabilities is not "interest-bearing borrowings"; face-only v1 cannot
  isolate borrowings, so `total_debt` = null with a specific warning and D/E = null (`missing_input`).
  **Needed before M2.4:** the tech lead updates `fixtures/expected/company_a.json` (`total_debt` null,
  plus warning) and `company_a.ratios.json` (D/E null, `reason: missing_input`). Code never edits them.
- M0 layout sign-off: yes. M1 top-10 sign-off: yes (tech lead, 2026-09-29).
- M2.1 allowed paths amended (MILESTONES): the gate calls `finintel locate` (finintel/cli) and the scripted
  check in `scripts/gate.py`, which the original list did not allow.
- Corporate vs other: "customer deposits" alone does not conflict with corporate (housebuilders,
  retailers); "loans and advances to customers", or any two bank signals, does. Tested both ways.

Fixed along the way (M1 bug): `PageText.width/height` came from PyMuPDF's rotated rect while word
coordinates are unrotated, so "top of page" was wrong on landscape pages. Now unrotated, with
`visual_bbox` for display space; `TEXT_LAYER_VERSION` 1 -> 2 so every cached text layer rebuilds.

Evidence for EXTRACTION section 1.1 (thresholds unchanged; the tech lead owns that document):
- Unilever statement pages have numeric-token share 0.26 / 0.29 < 0.30, so numeric density scores 0 on
  both. They still reach 0.80 on title, bookmark, header and vocabulary.

Carried into M2.2:
- Unilever p.141 holds the income statement AND the statement of comprehensive income; "Net profit"
  prints in both. The income-statement table must end at the "Consolidated statement of comprehensive
  income" heading, or `net_income` gets two candidates.
- Unilever's income statement has three value columns (2024, 2023, 2022); labels cover two.
- Lloyds' statement of changes in equity continues onto p.220 ("continued" marker): multi-page merge.

---

## M1 gate re-run — 2026-09-29 — green except sign-off

M1 green on the real fixtures. Unilever 2024 (305 pp., EUR m) and Lloyds 2024 (338 pp., £m) both
inspect cleanly. Labels validate (`validate_pack`: valid). PDF SHA-256 matches the label.

| Command | Result |
|---|---|
| `make ci` | exit 0: **213 passed, 0 skipped** |
| `finintel inspect fixtures/pdfs/company_a.pdf` (cold) | exit 0, 9.8 s; 297/305 pages with text (digitally born); `parser_skipped: ["azure_di"]` |
| `finintel inspect fixtures/pdfs/company_b.pdf` (cold) | exit 0, 12.7 s; 335/338 pages with text |
| second run, both | `vendor_calls=0`; text layer hit; 20/20 pdfplumber pages from cache |
| `summary.page_count` vs `company_a.json` | 305 = 305 |
| `uv run pytest tests/inspect -k holdout` | 13 passed |

Top-10 evidence for the sign-off: company_a balance sheet p.143 rank 2, income statement p.141 rank 3;
company_b balance sheet p.218 rank 1, income statement p.216 rank 2.

Carried into M2.1 (evidence, not yet changes):
- Unilever's statement pages have numeric-token share 0.2565 (p.141) and 0.2932 (p.143): below the
  0.30 density threshold in EXTRACTION section 1.1. Title, outline, header and vocabulary signals
  alone still clear 0.55.
- The parent-company balance sheet (p.197, "COMPANY ACCOUNTS UNILEVER PLC") ranks first by density.
  The company-scope exclusion is what keeps it out.
- Neither PDF defines page labels. The labelled folio ("138") must come from the printed footer.
- Unilever's income statement prints three years (2024, 2023, 2022); labels cover two.
- `total_debt` label = all face "Financial liabilities" (includes derivatives and other financial
  liabilities). Needs a tech-lead decision before M2.4.

---

## M1 — 2026-09-26 — built, gate BLOCKED on fixtures

M1 code complete and green offline. Gate blocked: `fixtures/pdfs/` empty; only `EXAMPLE_company_a.json`.
Not advancing to M2.1.

| Command | Result |
|---|---|
| `make ci` | exit 0: ruff clean, strict mypy clean (64 files), **211 passed, 1 skipped** (`test_fixture_pdfs`: no PDFs), contracts and scope up to date |
| `uv run python scripts/check_scope.py M1 --base m0` | exit 0 |
| `uv run pytest tests/inspect -k holdout` | 13 passed |
| `uv run finintel inspect fixtures/pdfs/company_a.pdf` | exit 1: `no such file`; `vendor_calls=0` |
| `make inspect` (`finintel inspect --fixtures`) | exit 1: `no PDFs found. fixtures/pdfs/ is filled by the tech lead` |
| 280-page synthetic report, cold / warm cache | 1.95 s / 0.22 s (text layer 995 ms, pdfplumber on 40 candidate pages 796 ms). Synthetic pages are lighter than a typeset report; re-measure on `company_a`. |

What `finintel inspect <pdf>` writes to `artifacts/inspect/{stem}/`: `summary.json` (document record,
digital-born score, engines run/skipped/failed, top-10 statement-titled pages, specific warnings, run
trace with per-stage cache status, ms, vendor calls and estimated cost), `pages.jsonl`, `outline.json`,
`text/`, `tables/` (raw pdfplumber, `lines` and `text` strategies), `thumbs/`, `azure/raw.json` when keyed.

Decisions taken inside M1 (no plan change):
- OQ-7 unanswered, so its default applies: Azure DI on the whole document; `--azure-pages` is the B flag.
- Owner-password-only PDFs are accepted (they open without a password; many annual reports restrict
  editing). Only PDFs that need a password to open are refused (`encrypted_pdf`).
- pdfplumber runs on candidate pages by default (top 20 ranked, plus any further statement-titled
  page, max 40); `--tables all` for every page. COST_AND_OPS: never pdfplumber on every page by default.
- An Azure failure of any kind degrades to `parser_failed: ["azure_di"]`, is never cached, and the
  local path completes. Found by a test: a non-httpx network error used to crash the whole run.

Open for the tech lead: the ROCE conflict between the session prompt and `CLAUDE.md` (see the M1 report).

---

## M0 — 2026-09-26 — green

M0 green on Python 3.12. `uv.lock` committed. Sign-off on package layout still open (tech lead).

| Command | Result |
|---|---|
| `uv lock` | resolved 28 packages |
| `make ci` | exit 0: ruff clean, 67 files formatted, strict mypy clean (44 files), 66 passed, contracts up to date, scope.yaml up to date, web guard passed |
| `uv run python scripts/check_scope.py M0 --base main` | exit 0 |
| `uv run python scripts/check_imports.py --forbid fitz,pdfplumber,httpx,anthropic,voyageai` | exit 0 |

Change to the gate machinery: `docs/STATUS.md` added to the G2 global allow-list (MILESTONES G2
row, regenerated `scripts/scope.yaml`), so every session can log here without failing G2.
