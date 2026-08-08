# Kaggle execution

Full data, training, and final inference run only in an approved private Kaggle environment.

Read-only checks:

```bash
kaggle competitions files rsna-knee-abnormality-detection
kaggle kernels status <owner>/<notebook-slug>
kaggle kernels output <owner>/<notebook-slug> -p artifacts/kaggle-output
```

Approval-gated writes:

```bash
kaggle kernels push -p kaggle/notebook
kaggle competitions submit rsna-knee-abnormality-detection -f submission.csv -m "<approved message>"
```

Do not run either write command without explicit human approval. Submission notebooks must have internet disabled, finish within nine hours, and create `submission.csv`.
