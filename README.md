# Yelp Data Extractor Balancer

A memory-efficient Python tool for extracting a balanced sample of Yelp Academic
Dataset reviews by business category and review rating.

The project streams the large Yelp review JSONL file instead of loading it into
memory, joins reviews to filtered business metadata, samples reviews by category
and rating stratum, and writes a clean UTF-8 CSV under a configurable size limit.

## What It Does

The pipeline:

- joins Yelp reviews to businesses by `business_id`;
- maps raw Yelp business categories to simplified labels;
- filters to target business categories such as restaurants, salons, spas,
  auto repair, hotels, medical offices, fitness, tours, and retail;
- samples reviews across three rating groups:
  - `1-2 stars`
  - `3 stars`
  - `4-5 stars`
- writes only the required output fields;
- verifies the final CSV size and lowers the per-stratum sample cap if needed.

## Why This Design

The Yelp review file is large, so a full pandas merge can use significant memory.
This project uses a streaming design:

```text
load target businesses -> stream reviews -> lookup join -> stratified reservoir sample -> write CSV
```

That keeps memory usage bounded while still selecting reviews randomly within
each category/rating stratum.

## Installation

Create and activate a virtual environment, then install the project:

```bash
python -m pip install -e .
```

After installation, the CLI command is available as:

```bash
yelp-balance
```

## Input Files

Download the Yelp Academic Dataset and place these files in `data/`:

```text
data/yelp_academic_dataset_business.json
data/yelp_academic_dataset_review.json
```

The raw dataset files are intentionally ignored by Git.

## Usage

Run with default paths:

```bash
yelp-balance
```

Run with explicit options:

```bash
yelp-balance \
  --businesses data/yelp_academic_dataset_business.json \
  --reviews data/yelp_academic_dataset_review.json \
  --output output/yelp_balanced_reviews.csv \
  --reviews-per-stratum 500 \
  --max-size-mb 30 \
  --random-state 42
```

You can also run the entry point directly:

```bash
python main.py
```

## Output Schema

The generated CSV contains exactly these columns:

```text
business_id
business_name
category
stars
review_text
review_date
```

Generated output files are written to `output/` by default and are ignored by
Git.

## Performance Note

On one local run, the project processed the Yelp review file in a little over
two minutes and produced a CSV of about 9.4 MB, well under the 30 MB limit.

Actual runtime will depend on disk speed, CPU, Python version, and dataset
location.

## Project Documentation

Additional notes are available in `docs/`:

- `docs/streaming_pipeline_design.md`
- `docs/git_documentation_and_reuse_guide.md`
- `docs/review_balancer_optimization_summary.md`

## Development Checks

Basic syntax check:

```bash
python -m py_compile main.py src/*.py
```

Check what will be committed:

```bash
git status --short
git ls-files
```

Do not commit raw Yelp data, generated CSV files, virtual environments, IDE
metadata, or Python cache files.
