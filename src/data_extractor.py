"""Streaming extraction logic for Yelp business and review JSONL files."""

import json
import logging
from pathlib import Path

from src.category_filter import CategoryFilter
from src.review_balancer import ReservoirReviewBalancer


logger = logging.getLogger(__name__)


class DataExtractor:
    """Extract balanced Yelp review rows from newline-delimited JSON files.

    Business records are filtered into a small lookup table first. Review records
    are then streamed line by line and sampled, which avoids loading the large
    Yelp review file into memory.
    """

    def __init__(
        self,
        business_path,
        review_path,
        reviews_per_stratum=500,
        random_state=42,
        category_filter=None,
    ):
        self.business_path = Path(business_path)
        self.review_path = Path(review_path)
        self.reviews_per_stratum = reviews_per_stratum
        self.random_state = random_state
        self.category_filter = category_filter or CategoryFilter()
        self._validate_inputs()

    def _validate_inputs(self):
        """Validate configured paths and sampling limits before extraction."""
        if self.reviews_per_stratum <= 0:
            raise ValueError("reviews_per_stratum must be greater than 0")
        if not self.business_path.is_file():
            raise FileNotFoundError(f"Business data file not found: {self.business_path}")
        if not self.review_path.is_file():
            raise FileNotFoundError(f"Review data file not found: {self.review_path}")

    @staticmethod
    def _require_field(record, field_name, line_number, file_label):
        """Return a required JSON field or raise an error with source context."""
        if field_name not in record or record[field_name] in (None, ''):
            raise ValueError(
                f"Missing required field '{field_name}' in {file_label} JSON on line {line_number}"
            )
        return record[field_name]

    @staticmethod
    def _parse_stars(stars, line_number):
        """Normalize a Yelp star value to an integer rating."""
        try:
            return int(float(stars))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid review stars value on line {line_number}: {stars}") from exc

    @staticmethod
    def _iter_jsonl_records(path, file_label):
        """Yield parsed JSON objects from a JSONL file with line numbers."""
        with path.open('r', encoding='utf-8') as input_file:
            for line_number, line in enumerate(input_file, start=1):
                if not line.strip():
                    yield line_number, None
                    continue

                try:
                    yield line_number, json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid {file_label} JSON on line {line_number}") from exc

    def load_target_businesses(self):
        """Load Yelp businesses that match the configured target categories."""
        businesses = {}
        scanned_count = 0
        skipped_count = 0

        logger.info("Loading target businesses from %s", self.business_path)

        for line_number, business in self._iter_jsonl_records(self.business_path, 'business'):
            if business is None:
                skipped_count += 1
                continue

            scanned_count += 1
            business_id = self._require_field(
                business,
                'business_id',
                line_number,
                'business',
            )
            category = self.category_filter.categorize_business(business.get('categories'))
            if category is None:
                skipped_count += 1
                continue

            businesses[business_id] = {
                'business_name': business.get('name', ''),
                'category': category,
            }

        logger.info(
            "Loaded %s target businesses from %s scanned records; skipped %s records",
            len(businesses),
            scanned_count,
            skipped_count,
        )
        return businesses

    def extract_balanced_rows(self):
        """Stream Yelp reviews and return sampled rows plus stratum counts."""
        businesses = self.load_target_businesses()
        if not businesses:
            logger.warning("No target businesses matched the configured categories")

        balancer = ReservoirReviewBalancer(
            reviews_per_stratum=self.reviews_per_stratum,
            random_state=self.random_state,
        )
        scanned_count = 0
        matched_count = 0
        skipped_count = 0

        logger.info("Scanning reviews from %s", self.review_path)
        for line_number, review in self._iter_jsonl_records(self.review_path, 'review'):
            if review is None:
                skipped_count += 1
                continue

            scanned_count += 1
            business_id = self._require_field(review, 'business_id', line_number, 'review')
            business = businesses.get(business_id)
            if business is None:
                skipped_count += 1
                continue

            stars = self._require_field(review, 'stars', line_number, 'review')
            # Rows are shaped for the final CSV before sampling so the reservoir
            # never stores unused source fields from the large Yelp records.
            balancer.add({
                'business_id': business_id,
                'business_name': business['business_name'],
                'category': business['category'],
                'stars': self._parse_stars(stars, line_number),
                'review_text': review.get('text', ''),
                'review_date': review.get('date', ''),
            })
            matched_count += 1

        rows = balancer.rows()
        counts_by_stratum = balancer.counts_by_stratum()
        logger.info(
            "Scanned %s reviews; matched %s eligible reviews; skipped %s reviews; sampled %s rows across %s strata",
            scanned_count,
            matched_count,
            skipped_count,
            len(rows),
            len(counts_by_stratum),
        )
        return rows, counts_by_stratum
