# Data Card

Status: public-schema baseline only; no competition files downloaded locally.

## Source and license

- Competition: RSNA Knee Abnormality Detection.
- Live size: 569.76 GB, 819,640 files.
- Types: DICOM and CSV.
- License: competition rules plus RSNA MIRA Dataset Research Use Agreement.
- Use: research/competition only; no clinical use, redistribution, download-link sharing, re-identification, or unauthorized access.

## Public schema

- `train.csv`: `StudyInstanceUID`, optional `PatientSex`, multilingual `Report`, and 12 partially populated binary targets.
- `train_series.csv`: study/series IDs, fluid sensitivity, fat suppression, and anatomical plane.
- `train_series/<StudyInstanceUID>/<SeriesInstanceUID>/<SOPInstanceUID>.dcm`: one image slice per file.
- Test metadata and DICOMs are replaced during scoring; Kaggle reports about 1,300 test studies.
- Typical series contain 20-45 slices (median 30), with a long tail to hundreds.
- Transfer syntaxes include uncompressed Explicit VR Little Endian, JPEG Lossless, JPEG 2000, and Implicit VR Little Endian.
- DICOMs retain an allowlist of 86 metadata tags.

## Expected shifts and hazards

- International sites, scanners, protocols, populations, languages, orientations, intensities, and resolutions vary.
- Label prevalence is not guaranteed to match across training, public, and private evaluation data.
- Patient/repeat identifiers and duplicate structure remain unverified until permitted aggregate inspection runs on Kaggle.

## Boundary

Full-data inspection and processing run only in permitted private Kaggle sessions. Local tests use synthetic DICOMs and schemas. Logs contain no report text, patient identifiers, or pixel dumps.
