# Chunk 5 Downstream Contract Audit

Date: 2026-08-22. Base: d3771e7. Evidence: source-code inspection only; no private data accessed.
Status: Chunk 5 is NOT PASSED (r14 terminal failed at review-plan). All downstream consumption is
provisional until Chunk 5 completes.

## What later chunks may consume from Chunk 5

The following interfaces are implemented and synthetic-tested in the current tree but have not been
promoted by completed human QA or full private-data execution.

### Series-slot representation

Source: `src/rsna_knee/data/series_slots.py`.

- Six fixed primary slots in order: sagittal_fluid_sensitive, sagittal_structural,
  coronal_fluid_sensitive, coronal_structural, axial_fluid_sensitive, axial_structural.
  Defined as `PrimarySeriesSlot` (StrEnum).
- Missing-series mask: tuple of six booleans aligned to slot order; true = missing/unusable.
  Field name: `missing_mask` on `SeriesSlotAssignment`.
- Additional/retained series: `additional_or_duplicate` tuple with candidate, original_slot,
  plane_source, and retention reasons. Additional-series support exists at the interface level;
  model-side handling is a downstream decision.
- Plane classification: organizer flags authoritative when recognized; validated IOP can recover
  missing/malformed plane. Fluid sensitivity never inferred from image content.
- Quality gating: blocked series cannot become a primary regardless of ranking score. Reasons:
  no_decodable_slices, decode_failure, invalid_geometry, missing_pixel_spacing,
  missing_slice_spacing, irregular_slice_spacing, duplicate_slices, missing_physical_coverage.
- Deterministic ranking: ascending key = (blocked_flag, -decode_fraction, spacing_CoV_or_inf,
  -coverage_or_inf, resolution_area_or_inf, -decoded_count, tie_break_key). Tie-break key must be
  an opaque lowercase SHA-256-style value.

### Tensor/cache format

Source: `src/rsna_knee/dicom/pipeline.py`.

- PreprocessedSeries contains: tensor (NDArray float32), channel_names, sampled_ordered_indices,
  sampled_projected_positions_mm, geometry, ledger, laterality, clipping_values,
  normalization_statistics, output_pixel_spacing_row_column_mm,
  output_affine_lps_slice_row_column, provenance (OutputProvenance).
- Default config (preprocessing.v1.json): minmax normalization with 1st–99th percentile clipping,
  sample_count=24, no local contrast, no adjacent-slice channels, no difference channel, no resize,
  no instance fallback for QA.
- Configuration hash travels inside OutputProvenance.configuration_hash (SHA-256 of canonical JSON).
- Provenance envelope: code_commit (40-hex), configuration_hash, dicom_library_versions,
  preprocessing_version ("dicom-model-v1"), source_manifest_version, input_checksum, output_checksum.
- Transformation ledger records ordered_input_checksums, per_slice rescale slope/intercept,
  photometric interpretation, monochrome1_inversion_applied, slice_axis orientation flag,
  native_in_plane_preserved, horizontal_flip_applied (always false), through_plane_resampling_applied
  (always false), in_plane_resize_from_to.
- Geometry includes ordering_basis, canonical_slice_normal_LPS, projected_positions_mm,
  image_positions_LPS, pixel_spacing, per_slice_spacing, consistency flags, affine matrix if regular,
  duplicate_pixel_groups.

### Canonical study identifiers inside the private boundary

- The pipeline does NOT retain StudyInstanceUID/SeriesInstanceUID/SOPInstanceUID in its outputs.
  DecodedSlice metadata carries sanitized fields only; paths and UIDs are deliberately excluded from
  results and error messages.
- The private manifest binds study identity outside the tensor payload via the source_manifest_version
  and private audit database. Later chunks must use the private manifest for patient/study grouping;
  they must NOT attempt to reconstruct UIDs from tensor payloads.
- The tie_break_key used for deterministic selection is an opaque hash, not a UID.

### Deterministic sample selection

Source: `deterministic_slice_indices` in pipeline.py.

- When sample_count is set, evenly spaced physical positions are selected from the ordered volume.
  The function returns original indices into the ordered slices, preserving position alignment.
- Sampled indices are recorded in sampled_ordered_indices; corresponding physical positions are in
  sampled_projected_positions_mm. Both travel with every PreprocessedSeries.
- No random seed enters this path; determinism comes from even physical spacing over the sorted axis.

### Expected Kaggle paths

- Competition data mounts under /kaggle/input/<slug>/train_series/<StudyUID>/<SeriesUID>/<SOP>.dcm
  and /kaggle/input/<slug>/test_series/... (public contract knowledge only).
- The r14 recovery accepts only /kaggle/input/<slug> or collision-safe /kaggle/input/<owner>/<slug>
  derived roots, requires exactly one match, and rejects all other layouts.
- Private bundle datasets mount separately from competition data; exact slugs remain inside Kaggle.

### Downstream configuration interface

- configs/preprocessing.v1.json is the frozen v1 preprocessing configuration.
- configs/competition.yaml loads docs/competition_contract/contract.yaml as single operational source.
- Model configs should reference the preprocessing version string "dicom-model-v1" and bind their own
  version + code commit + fold version + label version when created.
- Every artifact must record: code version, config hash, data-manifest version, fold version,
  preprocessing version, label version (per engineering invariants).

## Proven current behavior vs expected-but-unverified

| Item | Status | Evidence |
|---|---|---|
| Six-slot assignment + missing mask | Synthetic-tested locally; NOT promoted | tests/test_series_slots.py |
| Deterministic slice sampling | Synthetic-tested locally; NOT promoted | tests/test_dicom_pipeline.py |
| Transformation ledger completeness | Synthetic-tested locally; NOT promoted | same |
| Full private-data correctness | Awaiting Chunk 5 completion | r14 failed before replay |
| Human visual QA | Not started | human-only boundary not reached |
| Runtime performance on Kaggle GPU | Run A 7h21m20s / Run B 6h36m06s passed comparison | authenticated status |
| Deterministic artifact equality | Byte-exact comparison PASSed | authenticated status |
| Review-plan materialization | Terminal ERROR (input_discovery_invalid) | authenticated status |

## Assumptions

- The six-slot enum and mask semantics will remain stable after Chunk 5 passes.
- PreprocessingConfig defaults in preprocessing.v1.json represent the intended production values.
- The private manifest schema (manifest-v2) will provide patient/study grouping keys for folds.
- The nine-check human QA framework covers all critical visual-correctness gates needed for promotion.

## Unresolved questions

- Will additional-series tensors be included in the final cache or only primary slots?
- What cache serialization format will be used (NPZ, Zarr, custom)? Not defined in current code.
- How will test-time inference handle studies where zero slots are usable?
- Does the finalizer's human_review_summary.json include per-study pass/fail detail or aggregate only?

These questions do not block sprint work but must be answered before integration.

## Forbidden dependencies

- Later chunks MUST NOT depend on any specific StudyInstanceUID, SeriesInstanceUID, or SOPInstanceUID value.
- Later chunks MUST NOT assume raw DICOM pixel access after preprocessing; consume PreprocessedSeries tensors only.
- Later chunks MUST NOT bypass the missing_mask; a missing slot must produce zeros + explicit mask signal.
- Later chunks MUST NOT treat report-derived labels as expert ground truth (per LABEL_CARD).
- Later chunks MUST NOT construct folds without hard protected groups from the private audit.
