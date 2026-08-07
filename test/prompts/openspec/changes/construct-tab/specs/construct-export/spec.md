# Construct Export Specification

## Purpose

Persist a constructed, validated notebook into `NOTEBOOKS_DIR` (`test/prompts/notebooks/`) with a unique/versioned filename so the Audit tab's Scan DB can discover it — closing the construct → audit loop. Optionally export a flattened `.py` script alongside the `.ipynb`.

## Requirements

### Requirement: Save to NOTEBOOKS_DIR

The exporter MUST write the constructed notebook as a `.ipynb` file into `NOTEBOOKS_DIR` (`test/prompts/notebooks/`, the same directory the Audit tab's Scan DB scans). The directory MUST be created if missing.

#### Scenario: Notebook lands in Scan DB directory

- GIVEN a validated constructed notebook
- WHEN the user triggers export
- THEN a `.ipynb` file exists under `test/prompts/notebooks/`
- AND the Audit tab Scan DB lists it on its next scan

#### Scenario: Missing directory created

- GIVEN `NOTEBOOKS_DIR` does not exist
- WHEN export runs
- THEN the directory is created before writing
- AND the write succeeds

### Requirement: Unique versioned filename

The exporter MUST avoid overwriting existing files: when a target filename exists, it MUST append a version suffix (e.g., `name-v2.ipynb`, `name-v3.ipynb`) or another collision-free scheme.

#### Scenario: Collision gets versioned name

- GIVEN `analysis.ipynb` already exists in `NOTEBOOKS_DIR`
- WHEN the user exports a new notebook with the same base name
- THEN the new file is saved as `analysis-v2.ipynb`
- AND the original file is untouched

#### Scenario: Fresh name saved as-is

- GIVEN no file named `analysis.ipynb` exists
- WHEN the user exports it
- THEN the file is saved as `analysis.ipynb`
- AND the saved path is reported back

### Requirement: JSON export with optional Python script

The exporter MUST serialize the notebook as JSON (`.ipynb`). It SHOULD also write a flattened `.py` script (code cells concatenated with comments) when the user opts in via the UI.

#### Scenario: Optional .py export

- GIVEN the user enabled the Python-script option
- WHEN export runs
- THEN a `.py` file is written alongside the `.ipynb`
- AND the `.py` contains the concatenated code cells

#### Scenario: Python export skipped by default

- GIVEN the Python-script option is disabled
- WHEN export runs
- THEN only the `.ipynb` file is written

### Requirement: UI progress and status surface

The exporter MUST report progress and final status through the pipeline's `progress_cb` and the UI: success (with the saved path) or failure (with the error reason). Errors MUST NOT be silently swallowed.

#### Scenario: Export success surfaced

- GIVEN a successful export
- WHEN the exporter finishes
- THEN the UI shows the saved filename and directory
- AND the status indicates success

#### Scenario: Export failure surfaced

- GIVEN a write error (e.g., permission denied)
- WHEN the exporter fails
- THEN the UI shows a failure status
- AND the error reason is displayed
