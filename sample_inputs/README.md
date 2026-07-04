# Sample inputs

A small, hand-crafted, **deterministic** set designed to exercise every phase.
These files are committed and stable.

## Sources

- `recruiter.csv` — structured rows: `name,email,phone,current_company,title`.
- `notes.txt` — free-text recruiter notes, one blurb per candidate
  (regex-extracted, naturally low confidence).
- `ats.json` — an ATS export whose field names deliberately differ from ours
  (`applicant_name`, `contact.email_address`, `employer`, `github_handle`, …),
  exercising **field-remap**.
- `../fixtures/github/<login>.json` — recorded GitHub API responses (the
  deterministic default; `--live` is opt-in). A login is **discovered** from
  another source (the ATS `github_handle`) and the profile is loaded from here.

## The people and what each one seeds

| Person | Where | Deliberate feature | Seeds |
|--------|-------|--------------------|-------|
| **Jonathan / Jon Park** | csv + notes + ats + github (all share `jon.park@example.com`; ats+github share github login `jonpark`) | multi-source same person; name-spelling conflict "Jonathan"/"Jon" | **Tier-1 merge** (shared email/github), clean-corroborated confidence, share-discount, GitHub languages→skills |
| **Priya Nair** | csv only | phone `555-0188` — no country code, no region | phone **abstention** → `phones: []` + abstentions channel |
| **Michael Smith** (PM @ Acme) | csv only | shares a name with the next Michael, nothing else | **Tier-3 false-merge guard** |
| **Michael Smith** (freelance, London) | notes only | same name, different email/phone/company | **Tier-3 false-merge guard** |
| **Robert Chen** | csv **and** ats | same name + same company (`Globex`) + same email *domain*, but **different exact emails** (`robert.chen@` vs `r.chen@`) and no shared phone | **Tier-2 merge** (name + corroborator, no strong id) at cluster_conf 0.80 |
| **Dana Lee** | notes only | present only in notes | low-confidence profile |
| **Sofia Alvarez** | ats only | net-new person, no overlap | ATS field-remap; **singleton** |

## What entity resolution (P2) does with these

Blocking emits E:/P:/G:/N: keys; any shared key makes a candidate pair; the
matching cascade classifies each pair; Tier-1/Tier-2 edges union (union-find),
Tier-3 never unions.

- **Park** merges 4 records via **Tier-1** (shared email; also shared github
  login) → one profile, `cluster_conf` 0.97.
- **Robert Chen** merges 2 records via **Tier-2**: identical name + same
  company + same email domain, but no shared identifier → `cluster_conf` 0.80.
- **The two Michael Smiths** collide in the **same `N:` (metaphone) block**, so
  they *are* compared; the cascade reaches **Tier-3** (name only, no
  corroborator) and refuses to merge → two profiles + a `possible_duplicate`
  diagnostic. This is the false-merge guard, reached via the real cascade.
- **Priya, Dana, Sofia** are singletons (`cluster_conf` 1.0).

The run produces **7 profiles**.
