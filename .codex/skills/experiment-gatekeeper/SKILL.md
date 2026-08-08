---
name: experiment-gatekeeper
description: Gate proposed medical-imaging experiments before execution and completed experiments before promotion using scientific validity, leakage controls, reproducibility, provenance, competition compliance, resource limits, and complete out-of-fold evidence. Use for every experiment proposal, rerun, comparison, ensemble candidate, promotion decision, or material configuration change.
---

# Experiment Gatekeeper

## Trigger conditions

- Review any proposed experiment, rerun, ablation, tuning study, ensemble, or material configuration change before compute starts.
- Review a completed experiment before it becomes a baseline, ensemble component, submission candidate, or promoted model.

## Required inputs

- Current competition contract, `AGENTS.md`, `STATUS.md`, `DECISIONS.md`, `RISK_REGISTER.md`, and relevant cards.
- Testable hypothesis, one principal experimental factor or an explicit interaction hypothesis, and a named comparator.
- Validated config, code version, seed, data manifest, label, fold, and preprocessing versions plus config hash.
- Current label-quality and leakage audit decisions; external-asset provenance and license when applicable.
- Resource estimate and inference budget with safety margin.
- For promotion: out-of-fold predictions, macro AUC, every label AUC, uncertainty, runtime, memory, artifact size, and prediction-correlation evidence.

## Procedure

1. Classify the request as a pre-run or post-run gate and freeze its scope.
2. Verify competition eligibility, privacy boundaries, external-asset provenance, and any required human approval.
3. Confirm a falsifiable hypothesis, comparable baseline, one principal factor unless interaction is explicit, and success and stop criteria defined before results.
4. Confirm dependency lock, validated configuration, deterministic identifiers, synthetic checks, label-quality decision, leakage decision, and complete artifact-provenance fields.
5. Check that projected compute and inference fit the live limits with substantial safety margin. Do not authorize unusual spend.
6. For promotion, require reproducible out-of-fold evidence, macro AUC, all label AUCs, uncertainty, runtime, memory, size, and prediction correlations on identical eligible rows and folds.
7. Return `APPROVE`, `CONDITIONAL`, or `BLOCK`; list evidence for each check and exact conditions. Internal approval never replaces a human external-action gate.

## Forbidden actions

- Train, infer on competition data, submit, spend leaderboard quota, accept rules, change teams, merge, publish, or initiate unusual compute from this skill.
- Override missing leakage or label-quality evidence, competition rules, privacy boundaries, or human approval gates.
- Retrofit the hypothesis or success threshold after viewing results, promote from leaderboard score alone, or compare incompatible folds or label masks.
- Expose credentials, private URLs, raw data, reports, patient metadata, checkpoints, or prediction artifacts.

## Outputs

- Versioned gate record with experiment ID, hypothesis, comparator, principal factor, provenance identifiers, check-by-check evidence, and decision.
- Exact blocking issues or conditions, resource envelope, promotion status, and smallest safe next action.
- Proposed updates to `STATUS.md`, `DECISIONS.md`, `RISK_REGISTER.md`, and the experiment registry when their facts changed.

## Validation checks

- Trace every gate item to a current file, hash, audit result, test result, rule, or measured artifact.
- Confirm comparator and candidate use compatible data, folds, masks, preprocessing, and metric code.
- Confirm metrics are finite, include denominators and uncertainty, and cover the complete live label schema.
- Confirm artifact provenance records code, config, data manifest, folds, preprocessing, labels, and dependencies.
- Confirm the tested commit and config match the proposed or completed run.

## Failure behavior

- Return `BLOCK` for missing safety, compliance, leakage, label-integrity, reproducibility, provenance, or promotion evidence.
- Use `CONDITIONAL` only for explicit non-safety follow-ups that can be verified before execution or promotion.
- Stop and report only the category of exposure if sensitive material appears; do not echo it. Never invent evidence or approve by default.
