import argparse
import math

from src.data_extractor import DataExtractor
from src.output_generator import OutputGenerator


def build_dataset(
    business_path,
    review_path,
    output_path,
    reviews_per_stratum=500,
    max_size_mb=30,
    random_state=42,
):
    current_limit = reviews_per_stratum

    while current_limit > 0:
        extractor = DataExtractor(
            business_path=business_path,
            review_path=review_path,
            reviews_per_stratum=current_limit,
            random_state=random_state,
        )
        rows, counts_by_stratum = extractor.extract_balanced_rows()

        output = OutputGenerator(output_path=output_path, max_size_mb=max_size_mb)
        size_bytes = output.write_csv(rows)

        if output.is_under_size_limit():
            return {
                'output_path': str(output.output_path),
                'row_count': len(rows),
                'size_mb': output.size_mb(),
                'reviews_per_stratum': current_limit,
                'eligible_strata': len(counts_by_stratum),
            }

        reduction_factor = output.max_size_bytes / size_bytes
        next_limit = max(1, math.floor(current_limit * reduction_factor * 0.98))

        if next_limit >= current_limit:
            next_limit = current_limit - 1

        current_limit = next_limit

    raise RuntimeError("Could not produce a non-empty CSV under the configured size limit.")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract a balanced Yelp review CSV by simplified business category."
    )
    parser.add_argument(
        '--businesses',
        default='data/yelp_academic_dataset_business.json',
        help="Path to yelp_academic_dataset_business.json",
    )
    parser.add_argument(
        '--reviews',
        default='data/yelp_academic_dataset_review.json',
        help="Path to yelp_academic_dataset_review.json",
    )
    parser.add_argument(
        '--output',
        default='output/yelp_balanced_reviews.csv',
        help="Destination CSV path",
    )
    parser.add_argument(
        '--reviews-per-stratum',
        type=int,
        default=500,
        help="Maximum reviews per category/rating stratum before size adjustment",
    )
    parser.add_argument(
        '--max-size-mb',
        type=float,
        default=30,
        help="Maximum output CSV size in megabytes",
    )
    parser.add_argument(
        '--random-state',
        type=int,
        default=42,
        help="Seed for repeatable random sampling",
    )

    return parser.parse_args()


def main():
    args = parse_args()
    result = build_dataset(
        business_path=args.businesses,
        review_path=args.reviews,
        output_path=args.output,
        reviews_per_stratum=args.reviews_per_stratum,
        max_size_mb=args.max_size_mb,
        random_state=args.random_state,
    )

    print(
        f"Wrote {result['row_count']} rows to {result['output_path']} "
        f"({result['size_mb']:.2f} MB, {result['reviews_per_stratum']} per stratum)."
    )


if __name__ == '__main__':
    main()
