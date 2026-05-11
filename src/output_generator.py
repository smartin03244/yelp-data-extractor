import csv
from pathlib import Path


class OutputGenerator:
    OUTPUT_COLUMNS = [
        'business_id',
        'business_name',
        'category',
        'stars',
        'review_text',
        'review_date',
    ]

    def __init__(self, output_path, max_size_mb=30):
        self.output_path = Path(output_path)
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)

    def write_csv(self, rows):
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

        return self.output_path.stat().st_size

    def is_under_size_limit(self):
        return self.output_path.stat().st_size <= self.max_size_bytes

    def size_mb(self):
        return self.output_path.stat().st_size / (1024 * 1024)
