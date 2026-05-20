# Git Documentation and Reuse Guide

## Recommended Git Contents

This project should track source code, lightweight documentation, and small
configuration files. It should not track raw Yelp data, generated CSV outputs,
virtual environments, editor state, or Python cache files.

Recommended files to commit:

```text
.gitignore
pyproject.toml
main.py
tests/test_pipeline.py
src/__init__.py
src/category_filter.py
src/data_extractor.py
src/output_generator.py
src/review_balancer.py
docs/review_balancer_optimization_summary.md
docs/streaming_pipeline_design.md
docs/git_documentation_and_reuse_guide.md
```

Recommended files and directories to keep out of Git:

```text
data/yelp_academic_dataset_business.json
data/yelp_academic_dataset_review.json
output/
venv/
__pycache__/
*.pyc
.idea/
*.egg-info/
```

The raw Yelp files and generated CSV are reproducible inputs/outputs rather than
project source. Keeping them out of Git avoids a large repository and prevents
accidentally committing files that are expensive to clone.

## Documentation Worth Keeping

For a learning project, the most useful documentation is the kind that explains
why the code is shaped the way it is. The following documents are worth keeping:

| Document | Purpose |
| --- | --- |
| `docs/streaming_pipeline_design.md` | Explains the current architecture and optimization strategy. |
| `docs/review_balancer_optimization_summary.md` | Preserves the earlier pandas-oriented optimization notes. |
| `docs/git_documentation_and_reuse_guide.md` | Explains what to commit and how the techniques transfer to other projects. |

If this project grows, add these later:

- `README.md` at the repo root with setup, usage, and a short project summary.
- `docs/testing_strategy.md` with test cases and sample fixture design.
- `docs/category_mapping_notes.md` with category mapping decisions and known
  false positives.
- `docs/performance_notes.md` with runtime, memory use, and dataset-size
  observations from full runs.

## Suggested README Outline

A future root `README.md` should be shorter than the design docs. It should help
someone run the project quickly.

Suggested sections:

```text
# yelp-data-extractor

## What It Does
## Requirements
## Input Files
## Usage
## Output Schema
## Design Summary
## Development Notes
```

The README should link to the deeper docs instead of repeating all details.

## Current Git Ignore Policy

The current `.gitignore` already covers the most important generated and local
files:

```text
data/*.json
output/*
__pycache__/
*.pyc
venv/
*.egg-info/
```

One additional ignore rule is worth considering:

```text
.idea/
```

That directory contains local JetBrains/PyCharm project metadata. Some teams
commit selected IDE project files, but for a small learning project it is usually
cleaner to keep editor state out of Git.

## Techniques Used in This Project

### Streaming JSONL Processing

The Yelp dataset stores one JSON object per line. This makes it possible to read
one record at a time:

```text
open file -> read line -> parse JSON -> process -> discard or keep small result
```

This is useful whenever the full input is too large to fit comfortably in memory.

Other applications:

- processing application logs;
- scanning audit events;
- transforming exported analytics events;
- reading web crawl results;
- filtering large API dumps;
- preparing machine learning datasets from raw records.

### Lookup-Based Joins

Instead of merging two large tables, this project loads the smaller filtered
business dataset into a dictionary:

```text
business_id -> business metadata
```

Then each streamed review can be joined with a constant-time dictionary lookup.

Other applications:

- joining transaction records to account metadata;
- joining events to user profiles;
- enriching product clicks with catalog data;
- mapping IDs to labels before model training;
- validating records against a known allowlist.

This pattern works best when one side of the join is small enough to keep in
memory.

### Reservoir Sampling

Reservoir sampling selects a random sample from a stream without knowing the
final stream length in advance. This project applies it separately to each
category/rating stratum.

Other applications:

- sampling logs for manual review;
- selecting random training examples from a large corpus;
- building balanced evaluation datasets;
- monitoring representative events from a live stream;
- downsampling records before expensive downstream processing.

The important benefit is fairness: every eligible record in a stratum has a
chance to be selected, even though the pipeline only scans the file once.

### Stratified Sampling

The project does not sample from all reviews globally. It samples within groups:

```text
category + rating group
```

This prevents large categories or common star ratings from dominating the final
dataset.

Other applications:

- balanced sentiment datasets;
- demographic or geography-balanced survey samples;
- fraud/non-fraud training data;
- product category benchmark sets;
- quality assurance review batches.

Stratification is useful whenever the output needs coverage across important
subgroups rather than a purely proportional sample.

### Narrow Output Contracts

The CSV writer emits exactly the required columns and drops everything else.

Other applications:

- creating deliverables for clients or vendors;
- preparing public datasets with sensitive fields removed;
- exporting model-training files with stable schemas;
- reducing noisy operational data to a clean reporting format;
- enforcing compatibility with downstream import tools.

A narrow output contract makes the result predictable and lowers the risk of
accidentally leaking unneeded data.

### Actual File-Size Verification

The project checks the size of the generated CSV on disk instead of estimating
from memory usage. This matters because serialized formats have overhead from
encoding, delimiters, escaping, quoting, and newlines.

Other applications:

- preparing upload files with platform size limits;
- creating email-safe attachments;
- producing batch files for legacy systems;
- generating compressed or uncompressed exports with strict limits;
- controlling API payload sizes.

When a deliverable has an external constraint, verify the finished artifact, not
just the in-memory representation.

## Reusable Design Pattern

The core pattern is:

```text
load small reference data
stream large event data
filter early
enrich with lookup
sample or aggregate incrementally
write a narrow output
verify external constraints
```

That pattern applies to many data engineering tasks because it keeps memory use
bounded and makes each stage easy to test.

## Testing Ideas for Future Work

The project now includes a pytest smoke suite in `tests/test_pipeline.py`. These
tests use tiny temporary JSONL fixtures instead of the full Yelp dataset, which
makes them fast enough to run before every commit.

Current coverage includes:

- category names map to the expected simplified labels;
- non-target businesses are skipped;
- review rows are joined with the correct business name and simplified category;
- each stratum respects the configured cap;
- CSV output contains exactly the required columns;
- invalid configuration is rejected;
- missing input files are reported clearly;
- invalid review star values include the source line number.

Useful tests to add later:

- undersized strata keep all available rows;
- size-limit retry lowers the per-stratum cap;
- random sampling is repeatable when the same seed is used;
- malformed JSON reports the source file and line number.

Small hand-written JSONL fixtures are enough for most of these tests. The full
Yelp files should not be needed for routine automated testing.

## Practical Git Workflow

Before committing, check:

```bash
git status --short
python -m compileall main.py src
python main.py --help
pytest
```

Then review what changed:

```bash
git diff
```

Commit source and docs together when they explain the same design change. Keep
generated output files out of commits unless there is a deliberate reason to
track a tiny sample fixture.
