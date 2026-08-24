# Annotation Manual

Provisional v0. For human annotators and future model-assisted workflows.

## Core rules

1. Read the entire report before assigning any state. Never assign based on one phrase alone.
2. Use impression section preferentially when findings and impression disagree.
3. If you cannot determine a state, use "uncertain". Never guess between positive and negative.
4. If no relevant terminology appears anywhere, use "not_mentioned".
5. Always record evidence span text and section when assigning positive or uncertain.

## State definitions

| State | When to use |
|---|---|
| positive | Finding explicitly described as present in current clinical context. |
| negative | Finding explicitly stated absent, ruled out, normal, unremarkable, or within physiologic range. |
| uncertain | Finding suspected, possible, cannot be excluded, equivocal, hedged without commitment, or borderline. |
| not_mentioned | No relevant terminology appears anywhere in the report. |

## Common pitfalls

- Do NOT treat missing mention as negative. Many reports omit normal structures.
- Do NOT count degenerative/mucoid signal as a tear.
- Do NOT count old healed fractures as positive.
- Do NOT confuse bursal fluid with joint effusion.
- Do NOT assume laterality; check whether the finding specifies medial/lateral.
- Do NOT ignore post-surgical context; prior surgery changes what counts as new pathology.

## Evidence-span requirements

For every positive or uncertain assignment:

1. Copy the exact sentence(s) supporting your decision.
2. Note which section it came from (findings, impression, etc.).
3. If the report has multiple conflicting statements, include all of them and flag for adjudication.

## Severity and laterality

- Record severity qualitatively if mentioned but do NOT change label_state based on severity alone.
- Laterality must match the target column: "Medial Meniscus" requires medial-side description;
  generic "meniscal tear" without side specification should be flagged for adjudication.

## Post-operative studies

- Prior surgical changes are context, not automatic positives.
- Graft status is tracked under the ACL column but conceptually distinct from native ACL.
- New pathology superimposed on post-surgical anatomy still counts as positive.
- If unsure whether a finding is new or post-operative, use uncertain and note the ambiguity.

## Quality checks before submitting an annotation

1. Does my evidence span actually support the assigned state?
2. Did I check all sections (not just impression)?
3. Is there any mention of this structure I missed?
4. Would another annotator likely agree?
5. Have I avoided treating absence of mention as explicit negative?
