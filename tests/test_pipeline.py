import csv
import json

import pytest

from main import build_dataset
from src.category_filter import CategoryFilter
from src.data_extractor import DataExtractor
from src.output_generator import OutputGenerator


def write_jsonl(path, records):
    with path.open('w', encoding='utf-8') as output_file:
        for record in records:
            output_file.write(json.dumps(record))
            output_file.write('\n')


@pytest.fixture
def sample_files(tmp_path):
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


def test_category_filter_maps_known_categories():
    category_filter = CategoryFilter()

    assert category_filter.categorize_business('Restaurants, Pizza') == 'Restaurants'
    assert category_filter.categorize_business('Manicure, Pedicure') == 'Nail Salons'
    assert category_filter.categorize_business('Accountants') is None


def test_data_extractor_streams_and_samples_matching_reviews(sample_files):
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


def test_build_dataset_writes_expected_csv(sample_files, tmp_path):
    business_path, review_path = sample_files
    output_path = tmp_path / 'balanced_reviews.csv'

    result = build_dataset(
        business_path=business_path,
        review_path=review_path,
        output_path=output_path,
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


def test_build_dataset_rejects_invalid_sample_size(sample_files, tmp_path):
    business_path, review_path = sample_files

    with pytest.raises(ValueError, match='reviews_per_stratum must be greater than 0'):
        build_dataset(
            business_path=business_path,
            review_path=review_path,
            output_path=tmp_path / 'output.csv',
            reviews_per_stratum=0,
        )


def test_data_extractor_reports_missing_input_file(tmp_path):
    with pytest.raises(FileNotFoundError, match='Business data file not found'):
        DataExtractor(
            business_path=tmp_path / 'missing_businesses.json',
            review_path=tmp_path / 'missing_reviews.json',
        )


def test_data_extractor_reports_invalid_review_stars(tmp_path):
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
