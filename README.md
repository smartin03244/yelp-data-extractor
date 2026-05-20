# yelp-data-extractor

A memory-efficient Python tool for extracting a balanced sample of Yelp Academic
Dataset reviews by business category and review rating.

The project streams the large Yelp review JSONL file instead of loading it into
memory, joins reviews to filtered business metadata, samples reviews by category
and rating stratum, and writes a clean UTF-8 CSV under a configurable size limit.
If the first CSV is too large, the project downsamples the rows already in memory
instead of rescanning the full review file.

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
- writes the output fields listed in `config/output_columns.json`;
- verifies the final CSV size and lowers the per-stratum sample cap if needed.
- writes runtime logs to `logs/yelp-data-extractor.log`.

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

Or use the bundled setup installer:

```bash
bash setup/install.sh
./yelp-data-extractor --help
```

The installer lets you choose an OS-default install location, a custom location,
or a project-local `.venv`. It installs dependencies and creates a project-root
`./yelp-data-extractor` symlink. See `setup/USER_GUIDE.md` for the quick guide.

For development and testing, install the optional test dependency:

```bash
python -m pip install -e ".[dev]"
```

After installation, the CLI command is available as:

```bash
yelp-data-extractor
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
yelp-data-extractor
```

Run with explicit options:

```bash
yelp-data-extractor \
  --businesses data/yelp_academic_dataset_business.json \
  --reviews data/yelp_academic_dataset_review.json \
  --output output/yelp_balanced_reviews.csv \
  --columns-config config/output_columns.json \
  --reviews-per-stratum 500 \
  --max-size-mb 30 \
  --random-state 42 \
  --log-dir logs
```

You can also run the entry point directly:

```bash
python main.py
```

## Output Files

Generated CSV files are written to `output/` by default and are ignored by Git.
Relative output paths are kept under `output/`; for example, `reviews.csv`
becomes `output/reviews.csv`, and `exports/reviews.csv` becomes
`output/exports/reviews.csv`.

## Output Schema

The generated CSV columns are read from `config/output_columns.json`. The default
config contains:

```text
business_id
business_name
category
stars
review_text
review_date
```

Edit the `output_columns` list to choose a subset of the available fields or
change their order. Unsupported column names fail with a clear error so typos do
not silently produce blank output.

## Logging

Runtime logs are written to `logs/yelp-data-extractor.log` by default. The CLI
prints concise success or error messages to the console, while detailed tracebacks
are kept in the log file. Use `--log-level DEBUG` for more detail or
`--log-dir another_directory` to choose a different log directory.

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
- `docs/expansion_roadmap.md`

## License

This project is licensed under Creative Commons Attribution-NonCommercial 4.0.
See `LICENSE` for attribution, noncommercial use terms, and commercial licensing
contact information.

## Development Checks

Run these checks before committing:

```bash
python -m compileall main.py src
python main.py --help
pytest
```

Check what will be committed:

```bash
git status --short
git ls-files
```

The pytest suite uses small temporary JSONL fixtures, so it does not need the
full Yelp dataset.

Do not commit raw Yelp data, generated CSV files, runtime logs, virtual
environments, IDE metadata, or Python cache files.
