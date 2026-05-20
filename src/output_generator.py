import csv
import logging
from pathlib import Path


logger = logging.getLogger(__name__)


class OutputGenerator:
    """Write yelp-data-extractor rows to the required CSV schema."""

    OUTPUT_COLUMNS = [
        'business_id',
        'business_name',
        'category',
        'stars',
        'review_text',
        'review_date',
    ]

    def __init__(self, output_path, max_size_mb=30):
        """Create an output writer with a maximum CSV size in megabytes."""
        self.output_path = Path(output_path)
        if max_size_mb <= 0:
            raise ValueError("max_size_mb must be greater than 0")
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)

    def write_csv(self, rows):
        """Write sampled rows to CSV and return the resulting file size."""
        logger.info("Writing CSV output to %s", self.output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        with self.output_path.open('w', encoding='utf-8', newline='') as output_file:
            writer = csv.DictWriter(
                output_file,
                fieldnames=self.OUTPUT_COLUMNS,
                extrasaction='ignore',
            )
            writer.writeheader()

            for row in rows:
                writer.writerow({column: row.get(column, '') for column in self.OUTPUT_COLUMNS})

        size_bytes = self.output_path.stat().st_size
        logger.info("Wrote %s rows to %s (%.2f MB)", len(rows), self.output_path, self.size_mb())
        return size_bytes

    def is_under_size_limit(self):
        """Return True when the output file is at or below the size limit."""
        return self.output_path.stat().st_size <= self.max_size_bytes

    def size_mb(self):
        """Return the current output file size in megabytes."""
        return self.output_path.stat().st_size / (1024 * 1024)
