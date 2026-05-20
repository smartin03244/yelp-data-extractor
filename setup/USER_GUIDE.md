# yelp-data-extractor Setup Guide

## What This Installer Does

The installer script:

- asks where to install the virtual environment;
- creates the virtual environment in the selected location;
- creates `config/`, `logs/`, and `output/` under the application directory;
- installs the default output-column config if it is not already present;
- installs `yelp-data-extractor` and its dependencies;
- installs development dependencies, including `pytest`;
- creates a project-root launcher named `yelp-data-extractor`.

After setup, you can run the tool from the project root with:

```bash
./yelp-data-extractor --help
```

## Requirements

- Python 3.10 or newer
- Internet access for dependency installation
- A Unix-like shell with `bash`

If `python3` is not the Python you want to use, set `PYTHON_BIN`:

```bash
PYTHON_BIN=/path/to/python3 bash setup/install.sh
```

## Install

From the project root, run:

```bash
bash setup/install.sh
```

The installer menu offers:

```text
1) Default OS location
2) Choose a different location
3) Project-local install
```

The default OS location is:

- Linux: `$XDG_DATA_HOME/yelp-data-extractor` or `~/.local/share/yelp-data-extractor`
- macOS: `~/Library/Application Support/yelp-data-extractor`
- Windows shells such as Git Bash: `%LOCALAPPDATA%/yelp-data-extractor`
- Other Unix-like systems: `~/.yelp-data-extractor`

Choose option `2` to open the terminal file picker. The picker lets you browse
directories, choose the current directory, go to the parent directory, or enter a
path manually.

Choose option `3` for the old project-local behavior, which installs into:

```text
.venv
```

For options `1` and `2`, the selected install location is also the application
directory. For option `3`, the project root is the application directory and the
virtual environment is created under `.venv`.

For unattended installs, set `INSTALL_DIR` before running the script:

```bash
INSTALL_DIR="$HOME/apps/yelp-data-extractor" bash setup/install.sh
```

The script is safe to rerun. It reuses the existing virtual environment in the
selected install location and refreshes the `./yelp-data-extractor` launcher.

## Run With Default Paths

Place the Yelp Academic Dataset JSONL files in `data/`:

```text
data/yelp_academic_dataset_business.json
data/yelp_academic_dataset_review.json
```

Then run:

```bash
./yelp-data-extractor
```

By default:

- CSV output is written under the application `output/` directory;
- logs are written to the application `logs/yelp-data-extractor.log`;
- output columns are read from the application `config/output_columns.json`.

## Run With Explicit Options

```bash
./yelp-data-extractor \
  --businesses data/yelp_academic_dataset_business.json \
  --reviews data/yelp_academic_dataset_review.json \
  --output yelp_balanced_reviews.csv \
  --reviews-per-stratum 500 \
  --max-size-mb 30 \
  --random-state 42
```

Relative output paths are kept under `output/`, so the example above writes:

```text
output/yelp_balanced_reviews.csv
```

## Change Output Columns

Edit `config/output_columns.json` to choose the CSV columns and order:

```json
{
  "output_columns": [
    "business_id",
    "business_name",
    "category",
    "stars",
    "review_text",
    "review_date"
  ]
}
```

Unsupported, duplicate, or empty column names fail with a clear error.

## Verify The Install

Run:

```bash
./yelp-data-extractor --help
```

If you installed into the project-local `.venv`, you can also run:

```bash
.venv/bin/python -m pytest
```

If you installed into another location, use the Python inside that selected
virtual environment to run tests.
