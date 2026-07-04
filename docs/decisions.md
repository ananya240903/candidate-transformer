# **Decisions Log (video crib sheet)**

Running log of every non-obvious choice \+ a one-line why. This is the author's defense sheet for the demo and review. **Append a line whenever you make a non-trivial call.** Seeded below with the decisions already made in design.

| \# | Decision | Why |
| ----- | ----- | ----- |
| 1 | Claim-centric (fact-table) internal model | provenance/confidence/determinism fall out instead of being bolted on; sources become pluggable (open/closed) |
| 2 | Deterministic rule cascade for ER, not ML/probabilistic | spec demands deterministic \+ explainable; ML linkage is non-deterministic and needs labeled pairs to calibrate |
| 3 | Multi-pass blocking before matching | sub-quadratic at thousands; comparisons scale with block size, not n² |
| 4 | Tier-3 (name-only) never merges | a false merge silently corrupts two profiles — the dedup analogue of wrong-but-confident; under-merge is recoverable |
| 5 | Noisy-OR for agreement | correct diminishing returns under independence; bounded, monotonic |
| 6 | share-discount for single-valued conflict | makes "wrong-but-confident is worse than empty" numeric — a tie halves confidence |
| 7 | anchor gate on overall (not geometric mean) | punish missing *identity* specifically, without geometric mean's collateral collapse on optional fields |
| 8 | Confidence caps below 1.0 by construction (max b=0.95) | epistemic humility — nothing is ever certain |
| 9 | GitHub from fixtures by default, `--live` opt-in | live API breaks determinism \+ rate-limits at scale; flag keeps it real |
| 10 | Two failure lanes: config-error (load) vs missing-data (record) | a bad `from` path is a programmer error and must fail loudly; only data absence obeys `on_missing` |
| 11 | Validate the *projected output*, error-not-coerce | validating only input is the common miss; coercion is a small act of inventing |
| 12 | candidate\_id \= hash of strongest identity key | stateless \+ reproducible; cross-run stability would need a persistent crosswalk (descoped) |
| 13 | Trust \+ reliability \+ weight tables externalized as config | tunable, auditable, point-at-able in the video; not hardcoded magic |
| 14 | Multi-valued union vs single-valued pick | losing a real email/skill to "conflict resolution" is a bug; only genuinely single-valued fields pick a winner |
| 15 | OOV skills kept verbatim at low confidence | dropping an unrecognized real skill is a bug; tight fuzzy threshold avoids inventing skill identities |

### P0 (vertical slice) decisions

| # | Decision | Why |
| --- | --- | --- |
| P0-1 | Build the FULL canonical model now; P0 only populates some fields | later phases fill the rest without reshaping (open/closed); avoids a schema migration mid-project |
| P0-2 | Added `norm_quality` to the `Claim` type (not in s3's field list) | s6 requires per-claim norm_quality for `b = trust x rel x norm_quality`; the s3 list was incomplete, so the field was added rather than diverge from the math |
| P0-3 | P0 "single cluster" implemented as grouping by **exact normalized email** (else name) | reconciles the roadmap's "assume one candidate" with the 5-candidate sample set: it merges Park's two sources on shared email and exercises the merge reducer, while staying explicitly short of P2 blocking/cascade. Documented limitation: no phone-only match, no name-drift tolerance, no same-name guard yet |
| P0-4 | Output is always a JSON **array** of profiles (one per cluster) | forward-compatible with P2 producing many profiles; a single-candidate run is just an array of one |
| P0-5 | P0 `overall_confidence` = mean of present per-field confidences (placeholder) | the s8d formula (cluster_conf x base_overall x anchor gate) is P1; noisy-OR `support` (s8a) is already real because it is foundational and trivial |
| P0-6 | `include_confidence` sibling maps each output path to its **canonical root field's** confidence; 0.0 if the root had no claims | s9f keys by output path but a derived path (emails[0] -> primary_email) has no single canonical confidence yet; root-field confidence is the honest P0 approximation, per-value refinement is P1. No-claim -> 0.0 (honestly-empty), never borrowed from overall |
| P0-7 | Projection `normalize` hooks (E164, canonical) wired as **pass-through** in P0 | the engine plumbing (resolve -> normalize -> matrix) is the hard part and is built now; P1 drops the real `phonenumbers`/skill functions into `normalize_hooks.py` with zero engine changes |
| P0-8 | Scoring tables live in `data/scoring.json`, loaded by `scoring.py` | honors "externalized as config, not hardcoded magic" (decision #13) without a CLI flag |

### P1 (normalization, conflict resolution, confidence) decisions

| # | Decision | Why |
| --- | --- | --- |
| P1-1 | Uniform normalizer signature `(raw, ctx) -> NormResult` with an explicit abstain | makes "value+norm_quality OR abstention" a type, not a convention; one stage handles all fields the same way |
| P1-2 | Abstention is **two-policy**: email abstention DROPS the claim; phone/date/country abstention KEEPS a null claim + recorded failed method | faithful to s6 (email "invalid -> drop claim"; phone "abstain -> null + low conf"). An invalid email is likely not an address; an unparseable phone is a real datum we honestly failed to format |
| P1-3 | Abstained claims recorded in provenance as `<method>:<failed>_abstained` (e.g. `direct_field:e164_abstained`) | keeps the 3-key {field, source, method} provenance shape from the assignment while making the failed attempt visible & testable (the "recorded failed method") |
| P1-4 | Added `abstained` + `failed_method` to the `Claim` type | the internal currency must carry the abstention so merge can skip it for values yet surface it in provenance |
| P1-5 | Phone region inferred from a record's location/country claim if present, else `None` | s6; P1 inputs carry no location, so country-less numbers abstain (the headline case). The inference path is built & unit-tested (GB context) ready for sources that carry location |
| P1-6 | Single-valued winner chosen by **support** (ties: single-source trust, then lexicographic) | s7/s8; stated in code so the choice is deterministic. Strongest competing value drives the share-discount |
| P1-7 | Multi-valued field's scalar confidence (for base_overall/anchor) = **max** support among its values | s8d says anchor uses "best field_conf among emails" -> max; applied consistently to all multi-valued fields |
| P1-8 | A field whose only claims abstained is **absent** from `field_conf` (not a present field) | s8d base_overall is "over PRESENT fields"; an empty phones (all abstained) must not dilute the mean. The empty list still appears in the schema output |
| P1-9 | `cluster_conf` pinned to **1.0** with an explicit `>>> P2 will set this <<<` marker | real weakest-edge values (0.97/0.80) need entity-resolution edges that don't exist until P2. Consequence: corroborated/identified profiles score ~3% higher than s8e's targets (which assume 0.97) — documented, not hidden |
| P1-10 | date normalizer uses a **fixed** dateutil default (2000-01-01), never `now()` | determinism (invariant 2); we only emit YYYY-MM so a pinned default for absent fields is safe |
| P1-11 | Skill OOV kept verbatim at norm_quality 0.85; canonical/alias/fuzzy(>=90) at 1.0 | s6; tight threshold avoids inventing skill identities, OOV-keep avoids dropping a real skill |
| P1-12 | Date normalization: partial years (YYYY) preserved | Prevents silent "2000-01-01" fabrication for year-only inputs, which would pollute the date axis. |
| P1-13 | DROP_ON_ABSTAIN policy for 'emails' | Invalid syntax or normalization failure drops the claim; ensures we never emit a guessed or null-filled email. |

### P2 (entity resolution) decisions

| # | Decision | Why |
| --- | --- | --- |
| P2-1 | Abstentions moved OFF the provenance `method` string into a dedicated `abstentions: [{field,source,reason}]` channel | keeps provenance's fixed 3-key shape clean and gives P3's --explain a real, enumerable failure channel; replaces the P1 `direct_field:e164_abstained` hack |
| P2-2 | P0/P1 email-else-name grouping ripped out wholesale, replaced by blocking + cascade + union-find | the name-fallback branch had a latent false-merge; the cascade subsumes it and adds the Tier-3 guard |
| P2-3 | Free-mail domains (gmail/yahoo/…) excluded from the Tier-2 email-**domain** corroborator | a shared `gmail.com` is not corroboration; without this, two same-name gmail users would false-merge at Tier-2. Strengthens under-merge bias (not in the doc; a deliberate hardening) |
| P2-4 | Role/shared local-parts (info@, hr@, …) excluded from the identifier set (blocking **and** Tier-1) | s5a excludes them from blocking; extending to Tier-1 prevents a shared `info@` from anchoring a false strong-id merge |
| P2-5 | A block collision on **dissimilar** names → `NO_MATCH` (no edge, no diagnostic); Tier-3 is reserved for **similar** names lacking a corroborator | a metaphone clash between different names is noise, not a possible-duplicate; only genuinely ambiguous same-name pairs are surfaced |
| P2-6 | cluster_conf = **weakest merge-edge tier present in the component** (not a spanning-tree bridge analysis) | s8d intent ("weakest necessary edge") with a simple, defensible, conservative rule: any Tier-2 dependency caps the whole cluster at 0.80 |
| P2-7 | GitHub logins **discovered** from other sources (ATS `github_handle`), then loaded from `fixtures/github/<login>.json` (default) or `--live` | matches "discoverable from another source"; fixtures keep the default path deterministic; one code path for fixtures/live via a shared `from_profile` |
| P2-8 | `links.<sub>` handled as nested single-valued sub-fields in merge | lets github/ATS populate `links.github` in the canonical output without reshaping the claim model |
| P2-9 | GitHub fixtures dir defaults to a package-relative `<repo>/fixtures/github` | the default run (CLI or tests) includes GitHub deterministically regardless of the caller's cwd |
| P2-10 | Union-find attaches the lexicographically larger root under the smaller; nodes/edges processed sorted | deterministic component representative and assignment (invariant 2) |

## **Disclosed assumptions / known limitations (state in README)**

* Noisy-OR assumes source independence; sources partly correlate (ATS+CSV may share a typist) → mild over-confidence on correlated agreement. Known direction, not silent.  
* candidate\_id is not cross-run stable if the strongest identity key changes.  
* Single wildcard level only in `from` paths (no doubly-nested arrays).  
* Live LinkedIn, resume-PDF NLP, LLM extraction, persistent ID crosswalk: deliberately out of scope.

