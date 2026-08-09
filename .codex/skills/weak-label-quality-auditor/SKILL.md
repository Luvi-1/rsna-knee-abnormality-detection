---
name: weak-label-quality-auditor
description: Audit report-derived or otherwise weak medical-imaging labels for provenance, coverage, missingness, conflicts, and noise without treating them as expert ground truth. Use before weak-label dataset creation, fold construction, training, pseudo-labeling, thresholding, model promotion, or whenever label sources, extraction rules, or distributions change.
---

# Weak Label Quality Auditor

## Trigger conditions

- Audit a proposed or changed weak-label source, parser, ontology mapping, or merge rule.
- Gate folds, training, pseudo-labeling, evaluation, or promotion that depends on weak labels.
- Investigate aggregate label drift, missingness, conflicts, or implausible distributions.

## Required inputs

- Current competition contract, `LABEL_CARD.md`, `DECISIONS.md`, and applicable rules.
- Exact label schema and definitions; source, extraction method, and version for each label.
- De-identified aggregate counts for positive, negative, unknown, parse failure, and conflicts.
- Cohort, fold, manifest, preprocessing, and code versions used to produce the summaries.
- Any approved expert-adjudicated audit results, including sampling method and denominators.

## Procedure

1. Confirm that missing labels remain unknown and that weak labels are not expert ground truth.
2. Inventory each label's source, definition, temporal alignment, extraction logic, version, and known ambiguity.
3. Check aggregate coverage, class balance, unknown rate, parse-failure rate, source conflicts, co-occurrence, and fold consistency. Preserve denominators.
4. Compare versions only on an explicitly matched cohort. Identify asymmetric noise, systematic missingness, source drift, template artifacts, and ontology collisions.
5. Use supplied adjudicated results to quantify agreement, sensitivity, specificity, or predictive values where valid. Do not infer quality from prevalence alone.
6. Confirm that parsing rules, thresholds, calibration, and pseudo-label rules are fit within training folds only.
7. Return `PASS`, `CONDITIONAL`, or `BLOCK` with evidence, affected labels, and the smallest corrective action.

## Forbidden actions

- Read, print, transmit, or upload raw reports, DICOM pixels, patient-level metadata, or private competition artifacts outside the approved Kaggle environment.
- Treat missing or unparsed labels as negative, or call report-derived labels expert ground truth.
- Ask an LLM or external service to interpret private reports.
- Fit label rules on validation or test data, silently discard conflicts, or fabricate adjudication evidence.
- Train, submit, change teams, accept rules, or publish assets as part of the audit.

## Outputs

- Versioned audit report containing scope, inputs, aggregate checks, per-label findings, limitations, and evidence references.
- Explicit `PASS`, `CONDITIONAL`, or `BLOCK` decision with blocking issues and required follow-up.
- Proposed updates to `LABEL_CARD.md`, `RISK_REGISTER.md`, or the experiment record when their facts changed.

## Validation checks

- Match the exact live competition label schema; account for every label and every audited row.
- Verify that positive, negative, unknown, conflict, and failure counts use stated, compatible denominators.
- Confirm that comparisons use the same cohort or disclose cohort differences.
- Confirm that no patient identifiers, raw text, or private pixels appear in outputs.
- Trace every conclusion to a versioned aggregate, rule, or adjudicated result.

## Failure behavior

- Return `BLOCK` when provenance, denominators, schema, fold scope, or matched-cohort evidence is missing.
- Stop and report only the category of exposure if sensitive material appears; do not echo its contents.
- Resolve conflicting evidence conservatively and state what would remove the uncertainty. Never claim the labels are audited when a required check could not run.
