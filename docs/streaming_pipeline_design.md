# Yelp Review Extraction Streaming Pipeline Design

## Purpose

This project prepares a balanced CSV sample from the Yelp Academic Dataset by
joining review records with business category data, filtering to a fixed set of
simplified business categories, and sampling reviews across rating strata.

The important constraint is scale. The review dataset is several gigabytes, so
the design avoids loading all reviews or a full joined review/business table into
memory. Instead, it performs a small in-memory business lookup and streams the
large review file line by line.

## Requirements Summary

The final output must:

- join reviews to businesses by `business_id`;
- include only the target simplified business categories;
- sample up to 500 reviews per category/rating stratum;
- use three rating strata: `1-2 stars`, `3 stars`, and `4-5 stars`;
- preserve undersized strata without oversampling;
- choose reviews randomly, not by position or manual selection;
- write a UTF-8 CSV with a header row;
- read the output columns from `config/output_columns.json`, which defaults to:

```text
business_id,business_name,category,stars,review_text,review_date
```

- verify the final file is under 30MB;
- reduce the in-memory sample proportionally if the file is too large.
- write runtime logs to the configured log directory, `logs/` by default.

## High-Level Architecture

The current design is split into four responsibilities:

| Module | Responsibility |
| --- | --- |
| `src/category_filter.py` | Converts Yelp raw categories into the simplified project labels. |
| `src/data_extractor.py` | Loads target businesses and streams review records. |
| `src/review_balancer.py` | Samples reviews per category/rating stratum. |
| `src/output_generator.py` | Writes the final UTF-8 CSV and measures actual file size. |
| `config/output_columns.json` | Defines which sampled row fields are written to the CSV. |
| `main.py` | Orchestrates extraction, writing, and size-limit retries. |

This keeps the code easy to reason about:

- category logic is isolated from file I/O;
- extraction logic is isolated from CSV formatting;
- sampling logic can be tested independently;
- the CLI stays thin and focused on workflow.

## Data Flow

The pipeline runs in this order:

1. Read `yelp_academic_dataset_business.json` line by line.
2. Categorize each business using `CategoryFilter`.
3. Store only target businesses in memory:

```text
business_id -> {business_name, category}
```

4. Read `yelp_academic_dataset_review.json` line by line.
5. For each review, check whether its `business_id` exists in the filtered
   business lookup.
6. If it matches, construct the final output-shaped row.
7. Add the row to the reservoir sampler for its category/rating stratum.
8. Read the configured output columns from `config/output_columns.json`.
9. After streaming finishes, write sampled rows to CSV in the configured column
   order. Relative output paths are resolved under `output/`.
10. Check the actual CSV file size.
11. If the file is too large, lower the per-stratum cap, downsample the
    already-sampled rows, and rewrite the CSV.

## Why Streaming Instead of a Full Pandas Merge

A natural first version of this project is:

1. load businesses into a pandas DataFrame;
2. load reviews into a pandas DataFrame;
3. merge on `business_id`;
4. filter and sample from the joined DataFrame.

That design is simple, but it does not fit the Yelp review file well. The review
file is roughly 5GB as JSONL. Loading it into pandas can require much more than
5GB of RAM because strings, Python objects, DataFrame indexes, and intermediate
merge results all add overhead.

The streaming design avoids that memory spike. Only two things are held in
memory:

- the filtered business lookup, which is much smaller than the review file;
- the sampled review rows, capped by category/rating stratum.

With 10 categories, 3 rating strata, and 500 reviews per stratum, the intended
maximum sample is:

```text
10 * 3 * 500 = 15,000 rows
```

That is small enough to keep in memory comfortably.

## Sampling Strategy

The optimized sampler uses reservoir sampling per stratum.

Each stratum is identified by:

```text
(simplified_category, rating_group)
```

Examples:

```text
("Restaurants", "1-2 stars")
("Restaurants", "3 stars")
("Gyms & Fitness", "4-5 stars")
```

For each stratum, the sampler keeps at most `reviews_per_stratum` rows. When the
bucket is not full, new matching rows are appended. Once the bucket is full, each
new row gets a chance to replace an existing sampled row.

This matters because the review file is streamed once. We do not know how many
eligible reviews exist in a stratum until the scan is complete, so selecting the
first 500 would bias the sample toward earlier file order. Reservoir sampling
preserves random selection without needing all rows in memory.

## Size-Limit Strategy

The requirement is based on the final deliverable size, not an estimated memory
size. For that reason, `OutputGenerator` writes the CSV first and checks the
actual file size on disk.

If the file exceeds the configured limit, `main.py` calculates a lower
per-stratum cap:

```text
new_cap = current_cap * (max_allowed_bytes / actual_file_bytes) * safety_margin
```

The safety margin is currently `0.98`, which leaves a little room for CSV quoting
and row-length variation. The pipeline then downsamples the first-pass reservoir
sample using the smaller cap and rewrites the CSV.

This approach is more reliable than estimating size from a DataFrame, because
CSV size depends on UTF-8 encoding, delimiters, quotes, newlines, and review text
lengths. It also avoids rescanning the large Yelp review file when only the final
sample size needs to change.

## Category Mapping Design

`CategoryFilter` maps raw Yelp category text to one simplified project label.
It tokenizes category strings, lowercases them, and checks for configured
keywords.

This approach is intentionally simple and useful for a learning project, but it
has tradeoffs:

- A business can match multiple target categories, but the current design returns
  the first matching simplified category.
- Keyword mappings can create false positives, such as broad words like `food`,
  `store`, or `health`.
- Yelp category names are not normalized by this project beyond tokenization and
  simple singularization.

For future projects, consider replacing the keyword list with an explicit mapping
from Yelp category names to project labels when precision matters more than
convenience.

## Output Contract

The CSV writer reads the final schema from `config/output_columns.json`. The
default config is:

```text
business_id
business_name
category
stars
review_text
review_date
```

It uses `csv.DictWriter` with `extrasaction='ignore'`, so extra keys cannot leak
into the deliverable. The config is validated against the fields produced by the
extractor, so unsupported column names fail clearly instead of producing blank
cells. This lets users narrow or reorder the output without editing Python code.

## Logging and Error Handling

The CLI writes detailed runtime logs to a file. By default, logs are written to:

```text
logs/yelp-data-extractor.log
```

Expected operational failures, such as missing input files, invalid JSON, invalid
column config, and output write errors, are logged with traceback details. The
CLI prints a concise error message to stderr and exits with a nonzero status.

## Reproducibility

Sampling uses a configurable random seed, exposed as `--random-state` in the CLI.
Given the same input files, same per-stratum cap, and same seed, the sample
should be repeatable.

This is valuable for debugging because a surprising output row can be reproduced
without chasing nondeterministic sampling behavior.

## Running the Pipeline

Default run:

```bash
python main.py
```

Equivalent explicit run:

```bash
python main.py \
  --businesses data/yelp_academic_dataset_business.json \
  --reviews data/yelp_academic_dataset_review.json \
  --output output/yelp_balanced_reviews.csv \
  --columns-config config/output_columns.json \
  --reviews-per-stratum 500 \
  --max-size-mb 30 \
  --random-state 42 \
  --log-dir logs
```

The command prints the output path, row count, final file size, and final
per-stratum cap.

## Design Tradeoffs

### Benefits

- Handles large review files without loading them into memory.
- Keeps random sampling fair within each category/rating stratum.
- Enforces the exact output schema.
- Measures actual CSV size instead of relying on an estimate.
- Avoids rescanning the review file for size-limit retries.
- Keeps major responsibilities in separate classes.

### Costs

- If the first output is larger than 30MB, the pipeline rewrites the CSV from the
  bounded in-memory sample.
- The current category mapping is keyword-based and approximate.
- The sampled rows are held in memory at the end, although this is bounded by the
  stratum cap and category count.
- The existing pandas-based `ReviewBalancer` remains in the codebase as a useful
  comparison point, but the streaming path is better for the real Yelp file size.

## Future Improvements

Useful extensions for future versions:

- Add automated tests for category mapping, reservoir sampling, CSV schema, and
  size-limit retries.
- Add progress logging while scanning the large review file.
- Emit a summary report showing available and selected counts by stratum.
- Add stricter category mappings based on exact Yelp category names.
- Add support for compressed input files if the dataset is stored as `.json.gz`.

## General Lessons

The main lesson from this project is that the shape of the data should influence
the architecture. DataFrame-first designs are productive when data fits
comfortably in memory. For large JSONL files, streaming is often simpler and more
reliable.

Another reusable pattern is separating the pipeline into small roles:

- classify records;
- stream and filter input;
- sample or aggregate;
- write a narrow output contract;
- verify external constraints such as file size.

That pattern transfers well to future data preparation projects.
