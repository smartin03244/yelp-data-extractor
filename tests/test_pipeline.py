"""Regression tests for the yelp-data-extractor pipeline."""

import csv
import json
from pathlib import Path

import pytest

from main import build_dataset, resolve_output_path
from src.category_filter import CategoryFilter
from src.data_extractor import DataExtractor
from src.output_generator import OutputGenerator
from src.review_balancer import downsample_output_rows


def write_jsonl(path, records):
    """Write newline-delimited JSON records for pipeline tests."""
    with path.open('w', encoding='utf-8') as output_file:
        for record in records:
            output_file.write(json.dumps(record))
            output_file.write('\n')


@pytest.fixture
def sample_files(tmp_path):
    """Create small Yelp-like business and review fixtures."""
    business_path = tmp_path / 'businesses.json'
    review_path = tmp_path / 'reviews.json'

    write_jsonl(
        business_path,
        [
            {
                'business_id': 'restaurant-1',
                'name': 'Sample Cafe',
                'categories': 'Restaurants, Cafes',
            },
            {
                'business_id': 'auto-1',
                'name': 'Sample Auto',
                'categories': 'Auto Repair',
            },
            {
                'business_id': 'other-1',
                'name': 'Sample Accountant',
                'categories': 'Accountants',
            },
        ],
    )
    write_jsonl(
        review_path,
        [
            {
                'business_id': 'restaurant-1',
                'stars': 5,
                'text': 'Excellent.',
                'date': '2026-01-01',
            },
            {
                'business_id': 'restaurant-1',
                'stars': 2,
                'text': 'Slow.',
                'date': '2026-01-02',
            },
            {
                'business_id': 'auto-1',
                'stars': 3,
                'text': 'Fine.',
                'date': '2026-01-03',
            },
            {
                'business_id': 'other-1',
                'stars': 1,
                'text': 'Ignored.',
                'date': '2026-01-04',
            },
        ],
    )

    return business_path, review_path


@pytest.fixture
def columns_config_path(tmp_path):
    """Create a default output column config for tests."""
    config_path = tmp_path / 'output_columns.json'
    config_path.write_text(
        json.dumps({'output_columns': OutputGenerator.DEFAULT_OUTPUT_COLUMNS}),
        encoding='utf-8',
    )
    return config_path


def test_category_filter_maps_known_categories():
    """Known Yelp category strings should map to simplified labels."""
    category_filter = CategoryFilter()

    assert category_filter.categorize_business('Restaurants, Pizza') == 'Restaurants'
    assert category_filter.categorize_business('Manicure, Pedicure') == 'Nail Salons'
    assert category_filter.categorize_business('Accountants') is None


def test_data_extractor_streams_and_samples_matching_reviews(sample_files):
    """The extractor should join, filter, and sample matching review rows."""
    business_path, review_path = sample_files
    extractor = DataExtractor(
        business_path=business_path,
        review_path=review_path,
        reviews_per_stratum=2,
        random_state=42,
    )

    rows, counts_by_stratum = extractor.extract_balanced_rows()

    assert len(rows) == 3
    assert counts_by_stratum == {
        ('Auto Repair & Service', '3 stars'): 1,
        ('Restaurants', '1-2 stars'): 1,
        ('Restaurants', '4-5 stars'): 1,
    }
    assert {row['business_id'] for row in rows} == {'restaurant-1', 'auto-1'}
    assert all(row['business_name'] in {'Sample Cafe', 'Sample Auto'} for row in rows)


def test_build_dataset_writes_expected_csv(sample_files, columns_config_path, tmp_path):
    """The full build should write the default configured CSV schema."""
    business_path, review_path = sample_files
    output_path = tmp_path / 'balanced_reviews.csv'

    result = build_dataset(
        business_path=business_path,
        review_path=review_path,
        output_path=output_path,
        columns_config_path=columns_config_path,
        reviews_per_stratum=2,
        max_size_mb=1,
        random_state=42,
    )

    assert result['output_path'] == str(output_path)
    assert result['row_count'] == 3
    assert result['reviews_per_stratum'] == 2
    assert result['eligible_strata'] == 3

    with output_path.open('r', encoding='utf-8', newline='') as input_file:
        reader = csv.DictReader(input_file)
        rows = list(reader)

    assert reader.fieldnames == OutputGenerator.OUTPUT_COLUMNS
    assert len(rows) == 3
    assert {row['category'] for row in rows} == {'Restaurants', 'Auto Repair & Service'}


def test_build_dataset_uses_configured_output_columns(sample_files, tmp_path):
    """Custom output-column config should control CSV headers and values."""
    business_path, review_path = sample_files
    output_path = tmp_path / 'balanced_reviews.csv'
    columns_config_path = tmp_path / 'custom_columns.json'
    columns_config_path.write_text(
        json.dumps({'output_columns': ['business_name', 'stars']}),
        encoding='utf-8',
    )

    result = build_dataset(
        business_path=business_path,
        review_path=review_path,
        output_path=output_path,
        columns_config_path=columns_config_path,
        reviews_per_stratum=2,
        max_size_mb=1,
        random_state=42,
    )

    with output_path.open('r', encoding='utf-8', newline='') as input_file:
        reader = csv.DictReader(input_file)
        rows = list(reader)

    assert result['output_columns'] == ['business_name', 'stars']
    assert reader.fieldnames == ['business_name', 'stars']
    assert all(set(row) == {'business_name', 'stars'} for row in rows)


def test_build_dataset_downsamples_existing_rows_for_size_limit(tmp_path, monkeypatch):
    """Oversized output should be reduced without requiring another extraction."""
    business_path = tmp_path / 'businesses.json'
    review_path = tmp_path / 'reviews.json'
    output_path = tmp_path / 'balanced_reviews.csv'
    columns_config_path = tmp_path / 'output_columns.json'
    columns_config_path.write_text(
        json.dumps({'output_columns': OutputGenerator.DEFAULT_OUTPUT_COLUMNS}),
        encoding='utf-8',
    )

    write_jsonl(
        business_path,
        [
            {
                'business_id': 'restaurant-1',
                'name': 'Sample Cafe',
                'categories': 'Restaurants',
            },
        ],
    )
    write_jsonl(
        review_path,
        [
            {
                'business_id': 'restaurant-1',
                'stars': 5,
                'text': f"Excellent review {index}. " + ('x' * 200),
                'date': '2026-01-01',
            }
            for index in range(10)
        ],
    )

    extract_call_count = 0
    original_extract_balanced_rows = DataExtractor.extract_balanced_rows

    def count_extract_calls(extractor):
        """Count extraction calls while preserving real extractor behavior."""
        nonlocal extract_call_count
        extract_call_count += 1
        return original_extract_balanced_rows(extractor)

    monkeypatch.setattr(DataExtractor, 'extract_balanced_rows', count_extract_calls)

    result = build_dataset(
        business_path=business_path,
        review_path=review_path,
        output_path=output_path,
        columns_config_path=columns_config_path,
        reviews_per_stratum=10,
        max_size_mb=0.0004,
        random_state=42,
    )

    with output_path.open('r', encoding='utf-8', newline='') as input_file:
        rows = list(csv.DictReader(input_file))

    assert result['reviews_per_stratum'] < 10
    assert result['row_count'] == len(rows)
    assert output_path.stat().st_size <= 0.0004 * 1024 * 1024
    assert extract_call_count == 1


def test_downsample_output_rows_caps_each_stratum():
    """Output rows should be capped independently for each stratum."""
    rows = [
        {
            'business_id': f'restaurant-{index}',
            'business_name': 'Sample Cafe',
            'category': 'Restaurants',
            'stars': 5,
            'review_text': 'Good.',
            'review_date': '2026-01-01',
        }
        for index in range(5)
    ] + [
        {
            'business_id': f'auto-{index}',
            'business_name': 'Sample Auto',
            'category': 'Auto Repair & Service',
            'stars': 2,
            'review_text': 'Slow.',
            'review_date': '2026-01-01',
        }
        for index in range(5)
    ]

    sampled_rows = downsample_output_rows(rows, reviews_per_stratum=2, random_state=42)
    restaurants = [row for row in sampled_rows if row['category'] == 'Restaurants']
    auto_reviews = [row for row in sampled_rows if row['category'] == 'Auto Repair & Service']

    assert len(sampled_rows) == 4
    assert len(restaurants) == 2
    assert len(auto_reviews) == 2


def test_output_generator_rejects_invalid_column_config(tmp_path):
    """Invalid column config should fail before writing output."""
    config_path = tmp_path / 'invalid_columns.json'
    config_path.write_text(json.dumps({'output_columns': []}), encoding='utf-8')

    with pytest.raises(ValueError, match="non-empty 'output_columns' list"):
        OutputGenerator(output_path=tmp_path / 'output.csv', columns_config_path=config_path)


def test_output_generator_rejects_unsupported_columns(tmp_path):
    """Unsupported configured columns should fail instead of writing blanks."""
    config_path = tmp_path / 'unsupported_columns.json'
    config_path.write_text(json.dumps({'output_columns': ['business_name', 'unknown']}), encoding='utf-8')

    with pytest.raises(ValueError, match='unsupported columns: unknown'):
        OutputGenerator(output_path=tmp_path / 'output.csv', columns_config_path=config_path)


def test_resolve_output_path_puts_bare_filenames_in_output_directory():
    """Relative output paths should be written under the output directory."""
    assert resolve_output_path('reviews.csv') == Path('output/reviews.csv')
    assert resolve_output_path('exports/reviews.csv') == Path('output/exports/reviews.csv')
    assert resolve_output_path('output/reviews.csv') == Path('output/reviews.csv')


def test_build_dataset_rejects_invalid_sample_size(sample_files, columns_config_path, tmp_path):
    """The build should reject non-positive per-stratum limits."""
    business_path, review_path = sample_files

    with pytest.raises(ValueError, match='reviews_per_stratum must be greater than 0'):
        build_dataset(
            business_path=business_path,
            review_path=review_path,
            output_path=tmp_path / 'output.csv',
            columns_config_path=columns_config_path,
            reviews_per_stratum=0,
        )


def test_data_extractor_reports_missing_input_file(tmp_path):
    """Missing input paths should raise clear file errors."""
    with pytest.raises(FileNotFoundError, match='Business data file not found'):
        DataExtractor(
            business_path=tmp_path / 'missing_businesses.json',
            review_path=tmp_path / 'missing_reviews.json',
        )


def test_data_extractor_reports_invalid_review_stars(tmp_path):
    """Invalid star values should include the source review line number."""
    business_path = tmp_path / 'businesses.json'
    review_path = tmp_path / 'reviews.json'

    write_jsonl(
        business_path,
        [
            {
                'business_id': 'restaurant-1',
                'name': 'Sample Cafe',
                'categories': 'Restaurants',
            },
        ],
    )
    write_jsonl(
        review_path,
        [
            {
                'business_id': 'restaurant-1',
                'stars': 'not-a-rating',
                'text': 'Bad rating value.',
                'date': '2026-01-01',
            },
        ],
    )

    extractor = DataExtractor(business_path=business_path, review_path=review_path)

    with pytest.raises(ValueError, match='Invalid review stars value on line 1'):
        extractor.extract_balanced_rows()
