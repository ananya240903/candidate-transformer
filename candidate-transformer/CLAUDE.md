# **CLAUDE.md — Project Constitution**

This file is auto-loaded every session. It is the short list of things that must never be violated, regardless of which file you are working in. The full design lives in `docs/architecture.md`. The build order lives in `docs/roadmap.md`. **Read `docs/architecture.md` in full before writing any code.**

## **What this project is**

A multi-source candidate data transformer for a take-home assignment. Heterogeneous, partial, conflicting candidate data in → **one canonical, deduplicated, provenance-tracked, confidence-scored profile per real person** out, plus a runtime config that reshapes the output without engine changes.

The grader evaluates **judgment, not volume**. A smaller, sharper, fully-defensible system beats a sprawling one. The author must be able to explain and defend **every line** — so prefer readable, conventional code over clever code.

## **The thesis (the system's objective function)**

**Wrong-but-confident is worse than honestly-empty.**

This is not a slogan; it is the spec. It decides everything below. When in doubt, the system **abstains** (emits `null` \+ low confidence \+ a recorded failed method) rather than guessing a plausible value.

## **Non-negotiable invariants**

1. **Abstention, never invention.** A normalizer that cannot produce a confident result returns "unnormalizable" → `null` \+ low confidence. Never fabricate a value to satisfy a schema. The canonical example: a phone with no country code and no known region does **not** get a guessed country — it abstains.

2. **Determinism.** Same inputs → byte-identical output, always.

   * No live network calls in the default path (GitHub is served from **fixtures**; a `--live` flag is the only exception and is never the default).  
   * No random IDs, no wall-clock timestamps in IDs, no UUIDs.  
   * No unsorted set/dict iteration affecting output. Sort before you iterate anywhere order can leak into results (claims, clusters, fields, skills).  
3. **Claims are the internal currency.** Every source adapter decomposes its input into uniform, immutable **claims** (`entity_key, field_path, value, raw_value, source, method, source_trust`). Everything downstream — provenance, confidence, conflict resolution — operates on claims. Provenance is not a separate thing you populate; it **is** the set of claims behind a value. See architecture.md §3.

4. **Two failure lanes, never merged.**

   * A **malformed config path** (typo'd `from`, unknown field, unknown normalizer) is a programmer error → **hard error at config-load time**, before any record is touched. `on_missing` does NOT apply to it.  
   * A **missing value** (well-formed path resolving to nothing for a record) is a data gap → governed by `on_missing`. Silently returning `null` for a bad path is forbidden.  
5. **Validate the projected OUTPUT, not just the input.** Build the output schema dynamically from the config and validate the projected object after `on_missing` is applied. Type mismatches **error, never coerce** (coercion is a small act of inventing).

6. **Per-source isolation.** A missing or garbage source yields a diagnostic and **zero claims** — it never crashes the run. Wrap every adapter.

7. **Under-merge over false-merge.** In entity resolution, never merge two records on a weak signal (name alone). A duplicate profile is recoverable; a false merge silently corrupts two profiles — the dedup analogue of wrong-but-confident.

## **Guardrails (things you will otherwise "helpfully" get wrong)**

* **GitHub: fixtures by default.** Do not reach for the live API in the default path. Recorded JSON fixtures live in `fixtures/github/`. `--live` is opt-in only.  
* **Tests as you go, not at the end.** Each phase adds gold-profile / unit tests for what it built. Do not defer all testing to a final phase.  
* **Projection types: error, don't coerce.** If `from` resolves to a list where `type: string` was declared, raise — do not stringify.  
* **Confidence never reaches 1.0** by construction (max per-claim belief is 0.95). If you see a 1.0, something is wrong.  
* **No live LinkedIn, no resume-PDF NLP, no LLM extraction in the core path.** These are explicitly out of scope (see architecture.md §11). Do not add them.

## **How to work in this repo**

* **Follow the roadmap phases in order** (`docs/roadmap.md`). One git commit per completed phase. Each phase must end runnable and demoable.  
* **Do not one-shot the whole system.** Build the phase you're asked for, stop, and surface what happened (file tree, key diffs, anything surprising).  
* **Log every non-obvious decision** in `docs/decisions.md` with a one-line why. This file is the author's defense crib sheet for the demo video.  
* When the design doc and an "easier" approach conflict, **follow the design doc**; if you think the doc is wrong, say so and ask — don't silently diverge.  
* Keep functions pure and total where possible (normalizers, reducers, validators). The whole engine wants to be side-effect-free; only I/O lives at the edges.

