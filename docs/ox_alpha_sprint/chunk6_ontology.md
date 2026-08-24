# Chunk 6 — Provisional Medical Label Ontology

Date: 2026-08-22. Version: provisional-v0.

## Status

**NOT EXPERT-APPROVED.** This ontology is a research scaffold built from public medical terminology
and conservative clinical reasoning. Every rule and ambiguity resolution requires qualified
medical review before any training, submission, or clinical use.

## Design principles

1. **Four states only**: positive / negative / uncertain / not_mentioned. Not-mentioned is never negative.
2. **Evidence spans required** for positive and uncertain states so downstream review can audit decisions.
3. **Impression overrides findings** when they conflict; both are stored for adjudication.
4. **Severity does not flip state**: mild/moderate/severe positive is still positive; "mild narrowing" without other signs may be uncertain.
5. **Laterality must match target scope**: Medial Meniscus requires medial-side description; generic "meniscal tear" alone is insufficient.
6. **Every term list has provenance** from public radiology lexicon or explicit conservative reasoning documented here.

## Ambiguity resolutions (all flagged for review)

| Question | Provisional decision | Review priority |
|---|---|---|
| Meniscal degeneration vs tear | Degeneration is NOT a tear | High |
| Post-op meniscal morphology without new tear | NOT positive unless new tear stated | High |
| Mucoid ACL degeneration vs injury | Mucoid degeneration alone is NOT injury | High |
| ACL graft intact vs native normal | Separate concepts; graft status tracked under same column but distinct | High |
| Healed/chronic MCL change vs active injury | Chronic thickening without edema is NOT active | Medium |
| Trace physiologic fluid vs effusion | Trace fluid = NEGATIVE for effusion | Low |
| Effusion vs synovitis | Separate targets; neither implies the other | Low |
| Baker cyst vs generic popliteal abnormality | Requires classic location/communication | Medium |
| Traumatic contusion vs degenerative edema | Contusion needs trauma context or acute pattern | High |
| Acute vs healed fracture | Old healed fracture = NOT positive; stress/insufficiency = positive | Low |
| Cartilage damage vs compartment OA | Focal defect ≠ OA; compartment narrowing + osteophyte = OA | High |

## Target coverage summary

All 12 competition targets have entries in `configs/ontology/ontology_provisional_v0.yaml` with
positive/negative/uncertain term lists, related-findings exclusions, acute-vs-chronic handling,
postoperative handling, severity policy, laterality scope, and ambiguity notes.

## Known gaps requiring expert input

- Exact threshold language for OA grading (what distinguishes "mild narrowing" as uncertain vs negative).
- Whether "tiny effusion" should be uncertain or negative (currently uncertain).
- How to handle bilateral knee reports when only one knee is indexed by the study.
- Whether Pellegrini-Stieda should ever be positive if described as "recent" (currently always excluded).
- Synovitis detection on non-contrast MRI without enhancement (currently relies on thickening/proliferation terms only).

## Next steps after Chunk 5 passes

1. Route this document to a qualified reviewer (musculoskeletal radiologist or equivalent).
2. Record approval, rejection, or revision in DECISIONS.md with reviewer identity and date.
3. Only then promote to an approved version and bind it to label-engine configs.
4. Build weak-label rules that reference this ontology version explicitly.
