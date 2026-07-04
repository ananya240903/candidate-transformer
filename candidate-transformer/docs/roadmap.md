# **Roadmap — Build Order**

Build phases **in order**. Each ends **runnable, committable, and demoable** — partial-but-coherent beats complete-but-broken, and the demo video rewards an end-to-end run early. **One git commit per completed phase.** After each phase, stop and surface what happened (file tree \+ key diffs \+ anything surprising); do not roll straight into the next.

The guiding principle: at every checkpoint there is a working system that does *less*, never a half-built system that does nothing. If time collapses, ship P0+P1 cleanly and **write down** that P2+ are descoped — that honesty scores better than a half-built clustering stage that silently false-merges.

---

## **P0 — Vertical slice (the spine)**

**Goal:** end-to-end JSON out of real inputs. This alone is a passing submission.

Scope:

* Canonical pydantic model (`CanonicalProfile`) \+ `Claim` type.  
* One structured adapter (**CSV**) \+ one unstructured (**notes**), emitting claims.  
* Minimal normalizers: name, email.  
* Trivial merge: assume single cluster (one candidate), union/dedup multi-valued, first-by-trust for single-valued. (Real ER comes in P2.)  
* Projection interpreter handling the **default schema** \+ the **example config** from the assignment.  
* Output validation against the config-derived schema.  
* CLI: point at input files \+ a config, print/write JSON.

**Done when:** `cli` runs on sample CSV \+ notes, emits schema-valid JSON for both the default schema and the example custom config.

**Tests:** one gold-profile comparison for the happy path; one for the example config.

---

## **P1 — Make the hard parts real**

**Goal:** correctness on the things graders probe.

Scope:

* Phone → **E.164** with **honest abstention** (no-region unparseable → null).  
* Date → **YYYY-MM**; country → **ISO alpha-2**; skill canonicalization (alias map \+ tight rapidfuzz; OOV kept, not dropped).  
* Full conflict policy: `b = trust × rel × norm_quality`; single-valued winner with losers in provenance; multi-valued union.  
* Confidence: noisy-OR `support`, `share`\-discount, `field_conf`, weighted `base_overall`, `anchor` gate. (cluster\_conf can stay 1.0 until P2.)  
* Real provenance entries (`field → source → method` triples).

**Done when:** every field is normalized per spec, abstains correctly, and carries real provenance \+ per-field confidence.

**Tests:** the three §8e worked sanity checks as gold tests; phone-without-country → null; conflicting-name → mid confidence.

---

## **P2 — Entity resolution**

**Goal:** real dedup across multiple records, false-merge-safe.

Scope:

* Blocking (E/P/G/N keys) \+ tiered matching cascade (Tier-1/2/3) \+ union-find clustering; Tier-3 never unions (surfaced as `possible_duplicate`).  
* Deterministic `candidate_id` (hash of strongest identity key).  
* `cluster_conf` wired into overall (0.97 / 0.80 / 1.0 by weakest edge).  
* Add **ATS JSON** adapter (exercises field-remap) and **GitHub-from-fixtures** adapter (`languages → skills`).

**Done when:** two records of one person merge on a strong id; two distinct same-name people stay separate; ids are stable across runs on the same input.

**Tests:** two-people-one-name → no merge (gold); same-person-two-sources → one profile; ATS remap produces correct canonical fields.

---

## **P3 — Robustness \+ scale proof**

**Goal:** can't be crashed; scale story is real.

Scope:

* Per-source try/except isolation: garbage source → diagnostic \+ zero claims, run completes.  
* Full `on_missing × required` matrix incl. config-time vs record-time lanes; per-field override of global `on_missing`.  
* A synthetic \~10k-record run proving blocking keeps it sub-quadratic (timing note in README, not micro-optimization).  
* `--explain` diagnostics report: sources skipped \+ why, fields that abstained, clusters merged \+ on which tier.

**Done when:** a deliberately corrupt input file does not crash the run; the matrix behaves per the table; 10k run completes in reasonable time.

**Tests:** garbage-JSON source → run continues; each matrix cell; duplicate output `path` → config error; typo'd `from` → config error at load.

---

## **P4 — Tests \+ polish \+ submission**

**Goal:** submission-ready.

Scope:

* Round out gold-profile tests; ensure ≥1 covers a sharp edge case.  
* README: exact run steps, sample-input description, produced outputs committed under `outputs/`, assumptions \+ descopes stated.  
* `decisions.md` complete (the video crib sheet).  
* Optional minimal UI **only if** everything above is solid (CLI is fully sufficient).

**Done when:** fresh clone → README steps → green tests → produced JSON matches committed outputs. Demo video script ready: run end-to-end, show default \+ one custom config, talk through one design decision (suggest: noisy-OR confidence) \+ one edge case (suggest: phone-without-country or two-people-one-name).

---

## **Demo video targets (≈2 min)**

* Run pipeline end-to-end on sample inputs.  
* Show default output **and** ≥1 custom-config output.  
* One design decision to be proud of → **noisy-OR \+ share-discount confidence** (it's the thesis made numeric; point at the formula).  
* One edge case handled → **phone-without-country abstains to null**, or **two distinct same-name candidates do not merge** (Tier-3 guard).  
* 

