"""Command-line entry point for yelp-data-extractor."""

import argparse
import logging
import math
import os
import sys
from pathlib import Path

from src.data_extractor import DataExtractor
from src.output_generator import OutputGenerator
from src.review_balancer import downsample_output_rows


logger = logging.getLogger(__name__)
APP_DIR_ENV = 'YELP_DATA_EXTRACTOR_APP_DIR'
PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_FILENAME = 'yelp_balanced_reviews.csv'
DEFAULT_LOG_FILE = 'yelp-data-extractor.log'
EXPECTED_ERRORS = (FileNotFoundError, PermissionError, ValueError, RuntimeError, OSError)


def application_dir():
    """Return the directory that owns runtime config, logs, and output."""
    return Path(os.environ.get(APP_DIR_ENV, PROJECT_ROOT)).expanduser()


def default_config_dir():
    """Return the default application config directory."""
    return application_dir() / 'config'


def default_output_dir():
    """Return the default application output directory."""
    return application_dir() / 'output'


def default_log_dir():
    """Return the default application log directory."""
    return application_dir() / 'logs'


def default_columns_config_path():
    """Return the default output-columns config path."""
    return default_config_dir() / 'output_columns.json'


def configure_logging(log_level, log_dir=None, log_file=DEFAULT_LOG_FILE):
    """Configure file logging for the command-line interface."""
    log_dir = Path(log_dir) if log_dir is not None else default_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / log_file
    formatter = logging.Formatter('%(asctime)s %(levelname)s:%(name)s:%(message)s')

    logging.basicConfig(
        level=getattr(logging, log_level),
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
        ],
        force=True,
    )

    for handler in logging.getLogger().handlers:
        handler.setFormatter(formatter)

    logger.debug("Logging configured at %s; writing logs to %s", log_level, log_path)
    return log_path


def resolve_output_path(output_path, output_dir=None):
    """Return an output path that keeps relative exports under output_dir."""
    output_path = Path(output_path)
    output_dir = Path(output_dir) if output_dir is not None else default_output_dir()

    if output_path.is_absolute():
        return output_path

    if output_path.parts and output_path.parts[0] == output_dir.name:
        output_path = Path(*output_path.parts[1:]) if len(output_path.parts) > 1 else Path()

    try:
        output_path.relative_to(output_dir)
    except ValueError:
        return output_dir / output_path
    return output_path


def build_dataset(
    business_path,
    review_path,
    output_path,
    columns_config_path=None,
    reviews_per_stratum=500,
    max_size_mb=30,
    random_state=42,
):
    """Build a balanced Yelp review CSV that stays within the size limit.

    The extraction pass samples the requested number of reviews per stratum. If
    the finished CSV is too large, the pipeline lowers the per-stratum cap and
    rewrites a smaller CSV from the sampled rows already in memory.
    """
    if reviews_per_stratum <= 0:
        raise ValueError("reviews_per_stratum must be greater than 0")
    if max_size_mb <= 0:
        raise ValueError("max_size_mb must be greater than 0")

    output_path = Path(output_path)
    columns_config_path = columns_config_path or default_columns_config_path()
    logger.info(
        "Starting yelp-data-extractor build: businesses=%s reviews=%s output=%s columns_config=%s",
        business_path,
        review_path,
        output_path,
        columns_config_path,
    )

    extractor = DataExtractor(
        business_path=business_path,
        review_path=review_path,
        reviews_per_stratum=reviews_per_stratum,
        random_state=random_state,
    )
    extracted_rows, counts_by_stratum = extractor.extract_balanced_rows()
    output = OutputGenerator(
        output_path=output_path,
        max_size_mb=max_size_mb,
        columns_config_path=columns_config_path,
    )

    current_limit = reviews_per_stratum
    rows = extracted_rows

    while current_limit > 0:
        logger.info("Writing dataset with %s reviews per stratum", current_limit)
        size_bytes = output.write_csv(rows)

        if output.is_under_size_limit():
            logger.info("Output is under the %.2f MB size limit", max_size_mb)
            return {
                'output_path': str(output.output_path),
                'row_count': len(rows),
                'size_mb': output.size_mb(),
                'reviews_per_stratum': current_limit,
                'eligible_strata': len(counts_by_stratum),
                'output_columns': output.output_columns,
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
        if current_limit <= 0:
            break

        # Downsample the first-pass reservoir instead of rescanning the large
        # Yelp review file for every size-limit retry.
        rows = downsample_output_rows(
            extracted_rows,
            reviews_per_stratum=current_limit,
            random_state=random_state,
        )

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
        default=DEFAULT_OUTPUT_FILENAME,
        help="Destination CSV path. Relative paths are written under the application output directory.",
    )
    parser.add_argument(
        '--columns-config',
        default=str(default_columns_config_path()),
        help="JSON config file containing the output_columns list",
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
    parser.add_argument(
        '--log-dir',
        default=str(default_log_dir()),
        help="Directory where log files are written",
    )

    return parser.parse_args()


def build_dataset_from_args(args):
    """Resolve CLI arguments and run the dataset build."""
    return build_dataset(
        business_path=args.businesses,
        review_path=args.reviews,
        output_path=resolve_output_path(args.output),
        columns_config_path=args.columns_config,
        reviews_per_stratum=args.reviews_per_stratum,
        max_size_mb=args.max_size_mb,
        random_state=args.random_state,
    )


def print_success(result):
    """Print the successful build summary shown to CLI users."""
    print(
        f"Wrote {result['row_count']} rows to {result['output_path']} "
        f"({result['size_mb']:.2f} MB, {result['reviews_per_stratum']} per stratum)."
    )


def report_error(exc, log_path):
    """Log a handled failure and print a concise CLI error message."""
    logger.exception("Dataset build failed")
    print(f"Error: {exc}. See {log_path} for details.", file=sys.stderr)


def main():
    """Run the yelp-data-extractor command-line workflow."""
    args = parse_args()
    log_path = configure_logging(args.log_level, log_dir=args.log_dir)

    try:
        result = build_dataset_from_args(args)
    except EXPECTED_ERRORS as exc:
        report_error(exc, log_path)
        return 1
    except Exception as exc:
        report_error(exc, log_path)
        return 1

    print_success(result)
    return 0


if __name__ == '__main__':
    sys.exit(main())
