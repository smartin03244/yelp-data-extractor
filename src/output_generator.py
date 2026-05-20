"""CSV output and output-column configuration helpers."""

import csv
import json
import logging
from pathlib import Path


logger = logging.getLogger(__name__)


class OutputGenerator:
    """Write yelp-data-extractor rows to a configurable CSV schema."""

    DEFAULT_COLUMNS_CONFIG_PATH = Path('config/output_columns.json')
    DEFAULT_OUTPUT_COLUMNS = [
        'business_id',
        'business_name',
        'category',
        'stars',
        'review_text',
        'review_date',
    ]
    AVAILABLE_OUTPUT_COLUMNS = set(DEFAULT_OUTPUT_COLUMNS)
    OUTPUT_COLUMNS = DEFAULT_OUTPUT_COLUMNS

    def __init__(self, output_path, max_size_mb=30, columns_config_path=None):
        """Create an output writer with a size limit and column config path."""
        self.output_path = Path(output_path)
        if max_size_mb <= 0:
            raise ValueError("max_size_mb must be greater than 0")
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)
        self.columns_config_path = Path(columns_config_path or self.DEFAULT_COLUMNS_CONFIG_PATH)
        self.output_columns = self.load_output_columns(self.columns_config_path)

    @classmethod
    def load_output_columns(cls, columns_config_path):
        """Read and validate output column names from a JSON config file."""
        config_path = Path(columns_config_path)
        logger.debug("Loading output column config from %s", config_path)

        try:
            with config_path.open('r', encoding='utf-8') as config_file:
                config = json.load(config_file)
        except FileNotFoundError as exc:
            logger.error("Output column config file not found: %s", config_path)
            raise FileNotFoundError(f"Output column config file not found: {config_path}") from exc
        except json.JSONDecodeError as exc:
            logger.error("Output column config file is invalid JSON: %s", config_path)
            raise ValueError(f"Invalid JSON in output column config: {config_path}") from exc

        columns = config.get('output_columns') if isinstance(config, dict) else None
        cls._validate_output_columns(columns, config_path)
        logger.info("Loaded %s output columns from %s", len(columns), config_path)
        return columns

    @staticmethod
    def _validate_output_columns(columns, config_path):
        """Validate that configured output columns are usable CSV field names."""
        if not isinstance(columns, list) or not columns:
            raise ValueError(
                f"Output column config must define a non-empty 'output_columns' list: {config_path}"
            )

        invalid_columns = [column for column in columns if not isinstance(column, str) or not column]
        if invalid_columns:
            raise ValueError(f"Output column names must be non-empty strings: {config_path}")

        duplicate_columns = sorted({column for column in columns if columns.count(column) > 1})
        if duplicate_columns:
            raise ValueError(
                f"Output column config contains duplicate columns: {', '.join(duplicate_columns)}"
            )

        unknown_columns = sorted(set(columns) - OutputGenerator.AVAILABLE_OUTPUT_COLUMNS)
        if unknown_columns:
            raise ValueError(
                f"Output column config contains unsupported columns: {', '.join(unknown_columns)}"
            )

    def write_csv(self, rows):
        """Write sampled rows to CSV and return the resulting file size."""
        logger.info("Writing CSV output to %s", self.output_path)
        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)

            with self.output_path.open('w', encoding='utf-8', newline='') as output_file:
                writer = csv.DictWriter(
                    output_file,
                    fieldnames=self.output_columns,
                    extrasaction='ignore',
                )
                writer.writeheader()

                for row in rows:
                    writer.writerow({column: row.get(column, '') for column in self.output_columns})
        except OSError:
            logger.exception("Failed to write CSV output to %s", self.output_path)
            raise

        size_bytes = self.output_path.stat().st_size
        logger.info("Wrote %s rows to %s (%.2f MB)", len(rows), self.output_path, self.size_mb())
        return size_bytes

    def is_under_size_limit(self):
        """Return True when the output file is at or below the size limit."""
        return self.output_path.stat().st_size <= self.max_size_bytes

    def size_mb(self):
        """Return the current output file size in megabytes."""
        return self.output_path.stat().st_size / (1024 * 1024)
