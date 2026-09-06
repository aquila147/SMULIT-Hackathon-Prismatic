# What I fixed — changelog

Everything below is applied to the code in this zip. Compiles clean, imports
clean, startup tested, pipeline tested end to end with a stubbed LLM.

## Round 9 — three new features: portfolio risk, missing contracts, handoff summary

Backend is complete and tested end-to-end against a real database. **Frontend
components to display the two new endpoints still need to be built** — see the
"Frontend still needed" note at the end of this section.

### Feature 1 — Portfolio risk scoring (was entirely absent)

New file **`app/risk.py`** plus its prerequisite, new file
**`app/party_role.py`**.

- **Party-role detection** (`party_role.py`): identifies which party is the
  SME (the one appearing across the most contracts) and, per contract,
  whether the SME is supplier / customer / both / counterparty / unknown.
  Uses defined-term labels ('Acme ("the Supplier")'), payment direction, and
  contract type. Confidence-gated: weak signals return "unknown" rather than
  guessing, because risk direction inverts entirely by role.
- **Risk scoring** (`risk.py`): a curated table of market-norm rules. The
  tool can only raise a risk flag by SELECTING a pre-written assertion — it
  never generates a legal claim in free text, which makes a hallucinated
  legal assertion structurally impossible (same grounding-by-construction
  principle as the norms table discussed in the architecture docs). Rules are
  role-aware: a directional rule (e.g. "your liability is uncapped") fires
  only when the SME's role matches, and with unknown role only neutral rules
  fire. Only fields at VERIFIED/INFERRED confidence can raise a flag — never
  an ungrounded value. Deliberately produces a grouped summary by severity,
  never a single "risk score out of 100" (that false-precision number is
  exactly what the problem statement warns against).
- DB: new `risk_findings` table, `sme_party`/`sme_role`/etc. columns added to
  `contracts` via `ALTER ... ADD COLUMN` guarded so existing databases
  upgrade in place.
- API: `GET /api/risk` (portfolio-wide, grouped) and
  `GET /api/contracts/{id}/risk` (per contract).

### Feature 2 — Missing-contract / dangling-reference detection (was a bare schema stub)

New file **`app/gaps.py`**.

- Scans each contract for references to OTHER documents — a parent agreement
  an amendment modifies, a Schedule/Annex/Exhibit — and tries to resolve each
  against the rest of the corpus.
- Three outcomes, not two: **resolved** (strong match found), **ambiguous**
  (partial matches, shown with the reason each was rejected — e.g. "date
  mismatch: reference says 3 March 2022, candidate dated 2021-06-14"), and
  **unresolved** (nothing plausible).
- Strict language rule enforced in every output: never "you are missing a
  contract", always "we found a reference we could not resolve" — because an
  unresolved reference doesn't prove absence. The evidence is always a
  verbatim quote from a document we hold, so the finding is grounded either
  way. This is the "nobody knows what else is in there" scenario from the
  brief, and it needs no external data.
- DB: new `gaps` table. API: `GET /api/gaps`.

### Feature 3 — Handoff narrative summary (was a semicolon-joined field dump)

`_summarize_established()` in **`app/handoff.py`** rewritten. Was:
`"Verified fields: start_date: 2023-03-14; liability_cap: S$50,000"`. Now a
readable one-to-two paragraph brief describing the extraction method, what
reached high confidence, what's probable-but-unconfirmed, and specifically
what needs the lawyer's judgement and why — prose a lawyer can skim in
seconds. Feeds the existing `what_the_tool_established` field the frontend
already renders, so no frontend change needed for this one.

### Wiring

All three run in a new `_run_corpus_analysis()` in `main.py`, called once
after all uploads complete (they need every contract in the DB first). Each
step is isolated in its own try/except so one failing can't sink the others,
and risk/gaps recompute cleanly on each upload (DELETE then re-insert).

### Verified

Full end-to-end run against a real SQLite database with a stubbed LLM: SME
correctly identified across a 2-contract corpus; supplier role detected in the
MSA and counterparty in the NDA; uncapped-liability risk fired HIGH *because*
the role was supplier (would not fire for a customer); foreign-law and
long-notice flags fired; an unresolvable parent-MSA reference correctly
flagged as a gap. No exceptions anywhere in the chain.

### Frontend still needed

The backend endpoints (`/api/risk`, `/api/gaps`) return correct data now, but
the React app needs components to display them — a risk panel and a gaps
panel, analogous to the existing conflicts section. The handoff summary (3)
needs nothing further; it flows through the field the UI already shows. Until
the two panels are added, the data is reachable via the API but not visible in
the dashboard.

---

## Round 8 — semantic value normalization (the medium-confidence fix)

**The problem:** `resolve_field()` grouped claims by
`normalize_whitespace(value)` — which only cleans up spacing, soft hyphens,
and zero-width characters. It does nothing to reconcile values that mean the
same thing but are phrased differently. Four agents correctly finding a
90-day notice period but writing it as `"90"`, `"90 days"`,
`"ninety (90) days"`, and `"90 days"` formed **three separate groups**
instead of one — and `VERIFIED` requires `disagreement == 0`, so genuinely
agreeing agents were being scored as if they disagreed. This is the same
class of bug as the earlier int/string crashes, just showing up as a
suppressed score instead of an exception — no error in the logs, which is
why it went unnoticed until you pointed out most confidence levels weren't
great.

This was systemic, not localized: it affects every date, money amount, and
duration field where agents phrase the true value differently, which is most
fields, most of the time — consistent with confidence being broadly
mediocre across the corpus rather than bad on a couple of documents.

**Fix:** new file, **`app/value_normalize.py`**, with real semantic
normalizers:
- `normalize_date()` — "14 March 2023", "March 14, 2023", "2023-03-14" all
  become one ISO date string
- `normalize_duration_days()` — "90 days", "ninety (90) days", "3 months",
  and a bare "90" (Agent 1's typical output for this field) all become one
  day-count key
- `normalize_money()` — "S$50,000" and "SGD 50,000.00" become one canonical
  amount; deliberately does **not** guess when currency is genuinely
  ambiguous (see below)
- `normalize_party_name()` — "Acme Pte. Ltd." and "ACME PTE LTD" become the
  same key, same idea as the corpus-wide party normalization discussed
  earlier for role detection
- `normalize_boolean_ish()` — for yes/no-shaped fields like `exclusivity`

Wired into `verify.py`'s two grouping lines. Any field with no specific
normalizer falls back to exactly the old whitespace-only behaviour —
this can only make grouping **more** accurate, never less.

**One important side fix caught by testing before shipping:** the grouping
key is now a canonical internal string like `"DAYS:90"`, not
human-readable text. The first version of this fix stored that canonical key
directly as the field's displayed value, which would have shown users
`DAYS:90` instead of `90 days`. Caught this with a test before packaging —
`resolve_field()` now uses the canonical key only for grouping and the
confidence-tier math, and separately picks the actual displayed value from
the best-scoring claim's original, human-readable text.

**Verified, not just reasoned through:**
- The four-phrasing notice-period scenario above: after the fix, all four
  group together, confidence reaches `VERIFIED`, provenance `DIRECT`,
  displayed value is a real phrase like `"90"` — not the internal key.
- Three differently-formatted start dates: `VERIFIED`.
- Three liability cap phrasings: two correctly grouped (`S$50,000` /
  `SGD 50,000.00`), the third (`$50000`, ambiguous — `$` is used for both
  USD and SGD) correctly did **not** get silently folded in. This is
  intentional, not a bug — assuming `$` means the same currency as `S$`
  would be exactly the kind of invisible assumption the whole system is
  built to avoid. Worth knowing about if you see this on a real document:
  it means an agent dropped a currency-identifying character, which is
  itself useful information, not a normalization failure.

**What to expect:** confidence levels across the corpus should be
noticeably better on dates, money, and duration fields specifically —
nothing here changes span-gate behaviour, agent behaviour, or the
confidence-tier thresholds themselves. It only fixes what counts as
"the same answer" before those thresholds are applied.

---

## Round 7 — "database is locked" (a bug Round 6 introduced)

**Cause:** SQLite allows only ONE writer at a time, even in WAL mode. WAL
mode's benefit is that readers don't block writers and vice versa — it does
**not** let two connections write simultaneously. Round 6's
`_process_one_upload()` opened its database connection, inserted the
contract row, and then held that write transaction open through the ENTIRE
slow extraction pipeline (every LLM call, often 10-30+ seconds) before
finally committing at the end. With multiple documents now running
concurrently, several connections held open write transactions
simultaneously; only one could actually hold the lock, and everything else
queued until the connection's timeout (5 seconds, the sqlite3 default) and
then failed with exactly the reported error.

This was a correctness gap in the previous round's document-concurrency
change, not a new issue on your machine — worth being direct about, since
it was introduced by the fix meant to make things faster.

**Fix — two parts:**

1. **The actual fix, in `app/main.py`:** `_process_one_upload()` now does
   ALL of the slow work (ingest, extraction, verify, refute) with **no
   database connection open at all**. Only after every LLM call has
   returned does it open a connection, and every write — contract row,
   pages, fields, the final update — happens in one fast, uninterrupted
   burst, then commits and closes immediately. The write transaction's
   lifetime shrank from "the whole multi-second pipeline" to a handful of
   milliseconds of plain INSERT statements.

2. **A safety margin, in `app/db.py`:** `get_conn()` now passes
   `timeout=30.0` (was the 5-second default) — how long SQLite will wait
   for a lock to free before giving up. This alone would not have been
   enough on its own (a 30-second wait behind a 20-second-long open
   transaction just delays the same failure), which is why part 1 is the
   real fix and this is the backstop.

Also removed a leftover bug from the restructuring: a stray
`finally: db.close()` at the outer scope, referencing a `db` variable that
no longer existed there once the connection became local to the fast-write
block. Would have thrown `NameError` on every single document.

**Verified with a load test, not just reasoning about it:** simulated 8
documents processing concurrently, each doing 2 seconds of "LLM work."
- Old pattern (connection held open across the slow work): **7 of 8 failed**
  with `database is locked`, and the whole batch took 210 seconds (each
  failure burned its full timeout waiting for a lock that never freed).
- New pattern (connection opened only for the fast write burst at the end):
  **0 failures**, whole batch done in 2 seconds.

---

## Round 6 — comprehensive type-safety audit + major speed restructuring

This round did two things: (1) audited the whole codebase for the same class
of bug as the `notice_period_days` int crash, since it had now appeared
twice, and (2) rebuilt how the pipeline spends its time, since tuning
concurrency dials was reaching its limit as a speed lever.

### The crash: 'int' object has no attribute — wrong direction this time

Same bug family as before, opposite direction. Previously an LLM returned a
**number where text was expected** (`notice_period_days: 90` instead of
`"90"`). This time it returned **text where a number was expected**
(`quote_page: "0"` instead of `0`), crashing this comparison in
`verify.py`'s `span_gate`:

```python
if best_page is not None and 0 <= best_page < len(pages):
```

Python cannot compare an int to a string with `<=`, so this threw
`TypeError: '<=' not supported between instances of 'int' and 'str'` — and
because it happened inside the list comprehension building EVERY claim for a
document (`gated_claims = [span_gate(c, pages) for c in all_claims]`), one bad
page number from one agent again took down the whole document's results, same
as the earlier bug.

### The audit

Grepped every file for the same pattern: a value that originates from an
LLM's JSON response, used in a comparison, arithmetic operation, or string
method without being checked first. Found three exact call sites doing this
with page numbers — `app/extract.py` (Agent 2 and Agent 4's claim
construction) and `app/agent_retrieval.py` (Agent 3's). Everywhere else
(`conflicts.py`, `handoff.py`, `calendar_utils.py`'s confidence handling) was
already either using our own internally-computed values (safe by
construction) or already wrapped in a `try/except`.

### The fix — one shared module, not three scattered patches

New file: **`app/safe_types.py`**, with `coerce_page()`, `coerce_int()`, and
`coerce_str()`. The rule going forward: any LLM-derived field that is about to
be compared, sorted, or used in arithmetic goes through one of these first.

Applied at **both** ends of the pipeline for defence in depth:
- **At the point of failure** — `verify.py`'s `span_gate()` now coerces
  `quote_page` before comparing it, in both branches.
- **At the source** — `extract.py` (Agent 2, Agent 4) and
  `agent_retrieval.py` (Agent 3) now coerce `page` the moment a claim is
  built, so a bad type can never enter the system in the first place, not
  just get caught downstream.
- `calendar_utils.py`'s notice-period parsing now uses the shared
  `coerce_int()` instead of its own local regex, so there is one
  implementation of "make this an int safely," not several.

Verified with a reproduction test: a claim with `quote_page: "0"` (string)
now resolves cleanly with `quote_page` correctly coerced to `0` (int),
mixed with a normal claim in the same `verify_and_resolve()` call, no crash.

### Speed — the real fix, not another concurrency dial

Tuning `MAX_CONCURRENT_CALLS` up and down was treating the symptom. The
actual bottleneck was **how many LLM calls the pipeline makes at all**:

| Agent | Before | After |
|---|---|---|
| 2 (clause chunks) | ~8-15 calls (2000-char chunks) | ~4-8 calls (4000-char chunks) |
| 3 (retrieval) | ~10-12 calls (one per field) | **1 call** (all fields batched) |
| 4 (holistic) | 1 call | 1 call (unchanged) |
| 5 (refuter) | ~6-10 calls (one per field) | **1 call** (all fields batched) |
| **Total per document** | **~25-38 calls** | **~7-11 calls** |

**Agent 3 and Agent 5 rewritten to batch.** Both used to ask the LLM one
field at a time in a loop. Retrieval scoring (cheap, local, per-field) is
unchanged — only how the *results* get asked about changed: every field's
retrieved excerpts (or every attackable field's claimed value) now go into
ONE combined, clearly-labelled prompt, and the model returns one JSON array
covering all of them. Fewer round trips, and far fewer chances to collide
with a backend rate limit.

**Agent 2's chunk size raised** from 2000 to 4000 characters (`app/ingest.py`),
roughly halving its chunk count for a typical document, still comfortably
inside its 8192-token response budget.

**One global semaphore, not three uncoordinated local ones.** Added
`_GLOBAL_SEM` in `app/llm.py` — every single call to `complete()`, from any
agent, for any document, queues through this one gate. Removed the
per-agent semaphores in `extract.py` (Agent 3 and Agent 5 no longer need one,
since each now makes exactly one call). This is what makes the next change
safe:

**Documents are now processed concurrently, not one at a time.** Restructured
`app/main.py`: the whole per-file pipeline is now `_process_one_upload()`,
called via `asyncio.gather()` across every uploaded file instead of a
sequential `for` loop. This is safe because (a) `get_db()` opens a fresh
sqlite3 connection per call — confirmed by reading `app/db.py` before making
this change — and the DB runs in WAL mode, built for concurrent
connections, and (b) the global semaphore in `llm.py` caps total simultaneous
API requests regardless of how many documents are "in flight," so this
doesn't reopen the overload problem that caused the `finish_reason="error"`
failures.

**Verified together, not just individually:** ran 5 simulated documents
concurrently through the full real pipeline (extract → verify → refute) with
a stubbed LLM. Result: **5.0 LLM calls per document**, down from the
~25-38 estimated before this round — roughly a 5x reduction — with zero
crashes despite deliberately re-injecting both the int-value and
string-page bugs into the same run. Separately stress-tested the global
semaphore with 30 simultaneous callers (worse than any realistic case now):
peak actual concurrent requests observed was exactly 4, the configured
limit, regardless of how many callers competed for it.

**What this should feel like:** noticeably faster on the whole batch — both
because each document now needs far fewer round trips, and because multiple
documents proceed at once instead of queueing behind each other — and *more*
reliable under load, not less, since total simultaneous requests are now
centrally bounded instead of scattered across uncoordinated per-agent caps.

**The one dial that's still yours to turn:** `_GLOBAL_MAX_CONCURRENT` at the
top of `app/llm.py`, currently `4`. If you still see `finish_reason="error"`
after this, lower it. If the batch feels conservative and you have headroom
on your actual rate limit, raise it — but do it there, in one place, not
across three files.

---

## Round 5 — finish_reason=error, likely a concurrency side effect

**What it means:** unlike `length` (ran out of room) or empty content (the
model returned nothing), `error` specifically means the API/model backend
failed to generate the response — a provider-side or proxy-side hiccup. This
is usually **transient**, unlike `length` which is near-deterministic at
`temperature=0` — a retry has a real chance of succeeding.

**Likely cause — a side effect of the Round 2 speedup:** Agents 2, 3, and 4
run concurrently *with each other*, and Round 2 gave each of them its own cap
of 6 simultaneous requests. Combined, one document could throw **up to 13
simultaneous requests** at the same OpenRouter API key. If OpenRouter or the
DeepSeek backend enforces a per-key concurrency ceiling below that, some
requests get bounced back as `error` — not because anything is wrong with the
request, but from asking too much at once.

**Fix:** lowered `MAX_CONCURRENT_CALLS` from `6` to `3` in all three agents
(`app/extract.py`, `app/agent_retrieval.py`, `app/agent_refuter.py`). New
worst case per document: **7 simultaneous requests, down from 13** — still a
real speedup over the original one-at-a-time behaviour, with less pressure on
whatever concurrency limit the API is enforcing.

**If `finish_reason=error` still appears after this**, it's worth lowering
`MAX_CONCURRENT_CALLS` further (to `2`, even `1` to fully serialise one
agent) as a next step — that constant is the single dial for this trade-off,
present at the top of each of the three files.

---

## Round 4 fix — "Expecting value: line 1 column 1 (char 0)"

**What it means:** this is Python's JSON parser saying it found nothing valid
at the very start of the string it was asked to parse — in practice, this
means `json.loads("")` was called on an **empty string**.

**Why the earlier None-check didn't catch it:** the API can signal "no real
answer" two different ways — sending `content: null`, or sending
`content: ""` (an empty string). Round 3's fix only checked for `None`. An
empty string slipped straight past that guard, reached `json.loads("")`
further down, and crashed with this much more cryptic message instead of a
clear one.

**A second related trap in the same code:** if the model wraps its answer in
a markdown fence (` ```json ... ``` `) but the fenced block is itself empty,
the fence-stripping logic could also produce an empty string — same crash,
different path in. There was also a latent `IndexError` risk if a fence had no
newline to split on at all.

**Fix, in `app/llm.py`:**
- The guard now checks `content is None or not content.strip()` — catching
  `None`, `""`, and whitespace-only content in one place, with the message
  `"LLM returned empty content (finish_reason=...)"`.
- Fence-stripping is now safe against a fence with nothing after it (no
  `IndexError`), and if stripping the fence leaves nothing behind, that raises
  its own clear message too: `"LLM response was an empty code fence with no
  JSON inside"`.
- Genuinely malformed (non-empty) JSON still raises the normal
  `json.JSONDecodeError` — that path is untouched. Only the "nothing there at
  all" cases are now caught early with a clear reason.

Verified with a reproduction test covering five failure shapes (`None`, `""`,
whitespace-only, an empty ` ```json``` ` fence, an empty ` ``` ` fence with no
language tag) plus one real valid JSON payload — every failure case is now
caught with a specific message, and the real payload still parses correctly,
unaffected.

---

## Round 3 fix — finish_reason=length (token budget too small)

**What it means:** `finish_reason=length` is the API saying it hit the
response size limit (`max_tokens`) mid-answer and had to cut the model off.
This was a flat `4096` for every call.

**Why retries didn't help:** calls run at `temperature: 0`, so the model's
output length is close to deterministic — the same prompt tends to produce the
same length response every time. Retrying with the *same* 4096 limit was very
likely to hit the *same* wall again, which is exactly what happened (attempt 1
and attempt 2 both failed the same way). This wastes the full retry+backoff
delay on a failure that was never going to succeed without a bigger budget.

**Most likely source:** Agent 2 (`a2_clause`) and Agent 4 (`a4_holistic`) both
ask the model to return **up to 12 fields, each with a full verbatim quote, in
one response** — a JSON payload that can genuinely exceed 4096 tokens. Agent 3
and Agent 5 ask about one field at a time and were less likely to hit this.

**Fix, in `app/llm.py`:**
- `max_tokens` is now a parameter instead of a hardcoded `4096`, with a raised
  default of `8192`.
- Added an optional `label` parameter to `complete()` purely for logging — a
  failure now logs `LLM attempt 1/3 [a2_clause p.3-4] failed: ...` instead of
  the anonymous `LLM attempt 1/3 failed: ...`, so you can immediately see
  which agent and which part of the document is struggling.

**Per-agent budgets set at each call site:**
- Agent 2 (`extract.py`) → `max_tokens=8192`, labelled `a2_clause p.<pages>`
- Agent 4 (`extract.py`) → `max_tokens=12000` (the heaviest single call in the
  system: all 12 fields + quotes from up to 30k chars at once), labelled
  `a4_holistic`
- Agent 3 (`agent_retrieval.py`) → default budget, labelled
  `a3_retrieval:<field_name>`
- Agent 5 (`agent_refuter.py`) → default budget, labelled
  `a5_refuter:<field_name>`

Verified with a reproduction test: a simulated `finish_reason=length` failure
now logs with the field/agent label attached, confirming the diagnostic
improvement works as intended.

---

## Round 2 fixes (int-value crash + concurrency)

### The 'int' object has no attribute 'replace' crash

**Cause:** an LLM occasionally returns a numeric-sounding field
(`notice_period_days`, etc.) as a bare JSON number (`90`) instead of text
(`"90"`). `verify.py`'s `normalize_whitespace()` assumed every value was
already a string and called `.replace()` on it directly — a number has no
`.replace()` method, so this crashed.

**Why it mattered more than one field:** the crash happened inside
`resolve_field()`, called from `verify_and_resolve()`, with no per-field
try/except. One bad value type from ANY single agent on ANY single field
aborted resolution for the **entire document** — that is why
"Aegis - office support.docx" came back with zero fields.

**Fix, in `app/verify.py`:**
- `normalize_whitespace()` now coerces non-string input (`None`, `int`,
  `float`, `bool`) to text instead of assuming it is already a string. This is
  the single choke point every value passes through, so hardening it here
  fixes the bug for every field and every agent, not just this one case.
- `_value_in_quote()` had the same trap in a sneakier spot — it called
  `.lower()` on the raw value *before* normalizing it. Fixed the order:
  normalize (which now coerces to string) first, then lowercase.

**Same class of bug, found and fixed in `app/calendar_utils.py`:**
- `renewal_f.get("value", "").lower()` — wrapped in `str()` first.
- `re.sub(r"[^\d]", "", notice_f["value"])` — wrapped in `str()` first.
  This is the exact field (`notice_period_days`) that triggered the crash, so
  this was a live, not theoretical, second landmine on the same value.

Verified with a reproduction test: a claim with `value=90` (int) now resolves
cleanly to `'90'` (string) with no crash, instead of taking down the document.

### Speed — agents now ask their independent questions concurrently

**The problem:** Agent 2 (one call per document chunk), Agent 3 (one call per
field, ~12 fields), and Agent 5 (one call per attackable field) each looped
`for x in things: await llm.complete(...)` — asking one question, waiting for
the full reply, THEN asking the next. Each question is independent of the
others, so this waiting serves no purpose except making things slow.

**The fix:** each of the three loops now builds all its questions and fires
them together with `asyncio.gather()`, capped by `asyncio.Semaphore(6)` per
agent so one document's agents don't flood OpenRouter with unlimited
simultaneous requests (documents across an upload batch still run one after
another, so total in-flight requests stays bounded).

Changed files: `app/extract.py` (Agent 2's chunk loop), `app/agent_retrieval.py`
(Agent 3's field loop), `app/agent_refuter.py` (Agent 5's field loop).

**Measured in the test harness:** 15 simulated LLM calls (each with a fixed
0.3s "network" delay) completed in 0.61s instead of the ~4.5s+ a sequential
loop would take — roughly 7x faster on that call count. On a real document
with more fields/chunks the gain is larger, and it compounds across a whole
upload batch.

**What did NOT change:** nothing about what gets asked, or the answers you
get. Same questions, same model, same results — only the order calls are
fired in.

---

## Round 1 fixes

## The one that made everything look broken

**`init_llm()` now runs at startup** (`app/main.py`). Before, the web app never
initialised the LLM client, so every extractor threw `RuntimeError` which the
pipeline swallowed — the app "ran" but extracted nothing. Startup now:

- calls `init_llm()` with `OPENROUTER_API_KEY`
- **raises loudly if the key is missing** instead of failing silently
- honours an optional `LLM_MODEL` override

Set the key before starting:

```
PowerShell:  $env:OPENROUTER_API_KEY = "sk-or-..."
bash:        export OPENROUTER_API_KEY="sk-or-..."
uvicorn app.main:app --port 8000
```

## The five agents (was two)

The pipeline now runs the full ensemble. `extract_fields()` runs all four
extraction agents (Agent 5 runs later, at verify time):

| Agent | File | Pathway | LLM? |
|---|---|---|---|
| a1_rules | `app/agent_rules.py` **(new)** | deterministic regex | no |
| a2_clause | `app/extract.py` (extractor_a) | one chunk at a time | yes |
| a3_retrieval | `app/agent_retrieval.py` **(new)** | retrieved passages only | yes |
| a4_holistic | `app/extract.py` (extractor_b) | whole document | yes |
| a5_refuter | `app/agent_refuter.py` **(new)** | attacks resolved values | yes |

- **Agent 1 is the anchor.** Pure regex, no API, cannot hallucinate. When it
  agrees with an LLM agent, that is the only genuinely independent corroboration
  in the system. It emits `CANNOT_ASSESS` (never `ABSENT`) when a pattern misses.
- **Agent 3** uses pure-stdlib TF-IDF retrieval — no numpy, no
  sentence-transformers, nothing to install. Upgrade path to embeddings is noted
  in the file.
- **Agent 5** runs after `verify_and_resolve`, sees only the bare value + the
  document (never any agent's reasoning), and caps a field to `CONTESTED` when it
  can quote a genuine contradiction. Verified test: it downgrades on a real
  refutation and no-ops otherwise.
- Agents 2/3/4 run concurrently via `asyncio.gather`; Agent 1 runs first and
  unconditionally.

## Silent-failure removals

- **Un-swallowed the imports** in `main.py`. They were wrapped in
  `except (ImportError, Exception): x = None`, which hid any broken module. They
  now import directly, so a real error stops the app instead of quietly
  disabling a feature.
- **This immediately caught a dead feature:** CSV export imported
  `generate_results_csv` / `generate_coverage_csv`, which **do not exist** — the
  real functions are `export_results_csv` / `export_coverage_csv` with a
  different signature. The export endpoints already had a correct
  database-backed implementation, so I removed the broken import and the dead
  branches. Export now works off live DB data. (This feature was silently dead
  before — the judges score with it.)

## Smaller bugs

- **Extractor A no longer abandons a document after one bad chunk.** The `break`
  in its exception handler is now `continue` — one failed chunk skips that chunk
  only.
- **Deleted `data.db`** — it held stale test rows that would have shown up in the
  dashboard. It rebuilds fresh on first run.
- **Added `requirements.txt`** — the project had none.
- **Added `import logging`** to `main.py` (used by the new startup log line).

## Not changed (already correct — do not touch)

- `verify.py` span gate and three-state resolution: correct. Confirmed it
  discards a hallucinated quote (score 64 → discarded) and passes a real one
  (100). Confirmed `CONTESTED` fires only on genuine value disagreement, and
  `CANNOT_ASSESS` never counts as a vote.
- `ingest.py`, `conflicts.py`, `calendar_utils.py`, `handoff.py` — working and
  wired.

## Still worth knowing (not blocking)

- **Span gate threshold is 85, the design says 95.** 85 is more forgiving; fine
  for a weaker demo model. It is one constant in `verify.py` if you want to
  tighten it.
- **Extractor B truncates at 30,000 chars** — long contracts lose their tail,
  including schedules. Known limit; mention it rather than hide it.
- **Confirm the model string** `deepseek/deepseek-v4-flash-0731` matches what the
  organisers mandated and that your key has access.
- **Agent 3 sends most fields to the LLM** because TF-IDF against short passages
  always finds some overlap. That is safe: the LLM abstains on weak passages and
  the span gate discards any fabricated quote before voting.

## How to run

```
pip install -r requirements.txt
export OPENROUTER_API_KEY="sk-or-..."      # or $env: on PowerShell
uvicorn app.main:app --port 8000
# then upload the contracts in uploads/ through the UI
```

If it refuses to start complaining about the key, that is the fix working — set
the key.
