import argparse
import logging
import math

from src.data_extractor import DataExtractor
from src.output_generator import OutputGenerator


logger = logging.getLogger(__name__)


def configure_logging(log_level):
    """Configure process-wide logging for the command-line interface."""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(levelname)s:%(name)s:%(message)s',
    )


def build_dataset(
    business_path,
    review_path,
    output_path,
    reviews_per_stratum=500,
    max_size_mb=30,
    random_state=42,
):
    """Build a balanced Yelp review CSV that stays within the size limit.

    The first pass writes the requested number of reviews per stratum. If the
    finished CSV is too large, the pipeline lowers the per-stratum cap based on
    the measured file size and retries.
    """
    if reviews_per_stratum <= 0:
        raise ValueError("reviews_per_stratum must be greater than 0")
    if max_size_mb <= 0:
        raise ValueError("max_size_mb must be greater than 0")

    current_limit = reviews_per_stratum

    while current_limit > 0:
        logger.info("Building dataset with %s reviews per stratum", current_limit)
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
            logger.info("Output is under the %.2f MB size limit", max_size_mb)
            return {
                'output_path': str(output.output_path),
                'row_count': len(rows),
                'size_mb': output.size_mb(),
                'reviews_per_stratum': current_limit,
                'eligible_strata': len(counts_by_stratum),
            }

        reduction_factor = output.max_size_bytes / size_bytes
        next_limit = max(1, math.floor(current_limit * reduction_factor * 0.98))
        logger.warning(
            "Output exceeded %.2f MB; reducing reviews per stratum from %s to %s",
            max_size_mb,
            current_limit,
            next_limit,
        )

        if next_limit >= current_limit:
            next_limit = current_limit - 1

        current_limit = next_limit

    raise RuntimeError("Could not produce a non-empty CSV under the configured size limit.")


def parse_args():
    """Parse command-line arguments for yelp-data-extractor."""
    parser = argparse.ArgumentParser(
        description="yelp-data-extractor: extract a balanced Yelp review CSV by simplified business category."
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
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        default='INFO',
        help="Minimum logging level to display",
    )

    return parser.parse_args()


def main():
    """Run the yelp-data-extractor command-line workflow."""
    args = parse_args()
    configure_logging(args.log_level)

    try:
        result = build_dataset(
            business_path=args.businesses,
            review_path=args.reviews,
            output_path=args.output,
            reviews_per_stratum=args.reviews_per_stratum,
            max_size_mb=args.max_size_mb,
            random_state=args.random_state,
        )
    except Exception:
        logger.exception("Dataset build failed")
        raise
    else:
        print(
            f"Wrote {result['row_count']} rows to {result['output_path']} "
            f"({result['size_mb']:.2f} MB, {result['reviews_per_stratum']} per stratum)."
        )


if __name__ == '__main__':
    main()
