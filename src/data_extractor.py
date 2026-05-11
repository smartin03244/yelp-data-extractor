import json
from pathlib import Path

from src.category_filter import CategoryFilter
from src.review_balancer import ReservoirReviewBalancer


class DataExtractor:
    """
    Extracts a balanced review sample from Yelp JSONL files without loading the
    5GB review file into memory.
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

    def load_target_businesses(self):
        businesses = {}

        with self.business_path.open('r', encoding='utf-8') as business_file:
            for line_number, line in enumerate(business_file, start=1):
                if not line.strip():
                    continue

                try:
                    business = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid business JSON on line {line_number}") from exc

                category = self.category_filter.categorize_business(business.get('categories'))
                if category is None:
                    continue

                businesses[business['business_id']] = {
                    'business_name': business.get('name', ''),
                    'category': category,
                }

        return businesses

    def extract_balanced_rows(self):
        businesses = self.load_target_businesses()
        balancer = ReservoirReviewBalancer(
            reviews_per_stratum=self.reviews_per_stratum,
            random_state=self.random_state,
        )

        with self.review_path.open('r', encoding='utf-8') as review_file:
            for line_number, line in enumerate(review_file, start=1):
                if not line.strip():
                    continue

                try:
                    review = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid review JSON on line {line_number}") from exc

                business = businesses.get(review.get('business_id'))
                if business is None:
                    continue

                balancer.add({
                    'business_id': review['business_id'],
                    'business_name': business['business_name'],
                    'category': business['category'],
                    'stars': int(float(review['stars'])),
                    'review_text': review.get('text', ''),
                    'review_date': review.get('date', ''),
                })

        return balancer.rows(), balancer.counts_by_stratum()
