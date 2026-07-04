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

## **Disclosed assumptions / known limitations (state in README)**

* Noisy-OR assumes source independence; sources partly correlate (ATS+CSV may share a typist) → mild over-confidence on correlated agreement. Known direction, not silent.  
* candidate\_id is not cross-run stable if the strongest identity key changes.  
* Single wildcard level only in `from` paths (no doubly-nested arrays).  
* Live LinkedIn, resume-PDF NLP, LLM extraction, persistent ID crosswalk: deliberately out of scope.

