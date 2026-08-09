---
name: label-ontology-reviewer
description: Review knee-abnormality label definitions, canonical mappings, missingness masks, weak-label provenance, and submission ordering. Use before label ingestion, ontology or extraction changes, source merges, fold creation, training, metric computation, or submission validation.
---

# Label Ontology Reviewer

## Trigger conditions

- Run before creating or changing canonical labels, aliases, masks, extraction rules, folds, losses, metrics, or submission columns.
- Run before combining organizer labels with report-derived or external labels.
- Run when missingness, contradictions, granularity, laterality, or provenance is unclear.

## Required inputs

- Provide official target definitions and the current competition contract.
- Provide label schemas, mappings, masks, source/version provenance, and aggregate statistics.
- Provide the proposed extraction protocol for any weak labels, without raw report text.
- Provide the current `LABEL_CARD.md` and submission schema.

## Procedure

1. Establish the ordered canonical target list directly from official competition evidence.
2. Define each target's meaning, allowed encoded values, unknown representation, source, version, and exclusions.
3. Map aliases only with documented semantic evidence. Flag broader, narrower, ambiguous, negated, historical, and laterality-mismatched concepts.
4. Keep official labels, weak labels, pseudo-labels, and external labels in distinct provenance fields.
5. Treat missing labels as unknown and mask them from supervised loss and label-specific metrics.
6. Quantify aggregate coverage, prevalence among known labels, contradiction rates, and source overlap without exposing patient-level data.
7. Version the ontology and update the label card before downstream use.

## Forbidden actions

- Do not convert missing or unmentioned findings to negative.
- Do not call report-derived labels expert ground truth or merge weak labels into official labels without provenance.
- Do not send raw reports, report excerpts, patient metadata, private identifiers, or competition artifacts to an LLM or external service.
- Do not fit label rules, thresholds, or mappings on validation/test outcomes or change official submission order.
- Do not resolve semantic ambiguity by guessing.

## Outputs

- Produce a versioned canonical mapping and an updated label-card section.
- Produce aggregate coverage, prevalence, contradiction, and unresolved-mapping tables.
- Return a pass/block verdict for label ingestion, folds, training, evaluation, and submission use.

## Validation checks

- Confirm the canonical target set and order exactly match current official evidence.
- Confirm every encoded value has one meaning and every missing value remains masked.
- Confirm aliases are unique, reversible, provenance-preserving, and free of unresolved collisions.
- Confirm metrics exclude unknown targets per sample and reports distinguish known-label prevalence from total-row prevalence.
- Confirm outputs contain no raw reports, patient identifiers, credentials, private URLs, or private artifacts.

## Failure behavior

- Block downstream use when a target definition, alias, mask, provenance field, or submission position is unresolved.
- Preserve ambiguous concepts as unknown and record the exact evidence needed to resolve them.
- Never coerce, drop, or relabel ambiguous records merely to satisfy a schema.
