# Risk Register

| ID | Risk | Likelihood | Impact | Mitigation / gate | Status |
|---|---|---:|---:|---|---|
| R-001 | Kaggle identity verification is incomplete, potentially blocking participation or prize eligibility. | High | Critical | User completes Kaggle/Persona verification; verify status before submissions or compute spend. | Open |
| R-002 | No private GitHub source-of-truth or remote backup exists. | High | High | Create/select a private `Luvi-1` repository with explicit approval, then protect access. | Open |
| R-003 | Fine-grained GitHub token currently has no private-repository visibility. | High | High | Grant only the approved repository after creation; verify `Luvi-1` before every write. | Open |
| R-004 | Only a small label subset is official; report-derived labels may be noisy, multilingual, and missing-not-at-random. | High | Critical | Unknown masks, manual validation, provenance, per-label confidence intervals, and versioned label card. | Open |
| R-005 | Patient/repeat/duplicate/report-template leakage could inflate validation. | High | Critical | Build identity and similarity groups before folds; audit every split. | Open |
| R-006 | Final notebook may exceed the nine-hour offline runtime. | Medium | Critical | Benchmark inference early and retain a substantial safety margin. | Open |
| R-007 | MIRA prohibits dataset redistribution, download-link sharing, re-identification, clinical use, and derivative works; the interaction between the derivative-work clause and model artifacts needs conservative handling. | Medium | Critical | Keep data private, never re-identify, document transformations, and seek organizer clarification before public derived artifacts outside explicit winner obligations. | Open |
| R-008 | Rules prohibit private code/data sharing outside the official Kaggle team. | Medium | Critical | Limit private repo access to recognized team members; do not invite collaborators before team/access review. | Open |
| R-009 | Winner-license text names CC-BY-NC 4.0 while also describing an OSI license that does not limit commercial use. | Medium | High | Treat as a rules ambiguity; obtain organizer clarification before depending on license interpretation. | Open |
| R-010 | Public leaderboard overfitting could harm private rank. | Medium | High | Use locked OOF validation; treat leaderboard results as weak evidence only. | Open |
