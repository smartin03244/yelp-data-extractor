"""Review sampling utilities for balanced Yelp review exports."""

import random
from collections import defaultdict


def group_output_rows_by_stratum(rows):
    """Group output-shaped review rows by category and rating stratum."""
    grouped_rows = defaultdict(list)
    for row in rows:
        rating_group = ReservoirReviewBalancer.rating_group(row['stars'])
        if rating_group is not None:
            grouped_rows[(row['category'], rating_group)].append(row)
    return grouped_rows


def downsample_output_rows(rows, reviews_per_stratum, random_state=42):
    """Return rows capped per category/rating stratum without rescanning input."""
    if reviews_per_stratum <= 0:
        raise ValueError("reviews_per_stratum must be greater than 0")

    randomizer = random.Random(random_state)
    grouped_rows = group_output_rows_by_stratum(rows)
    sampled_groups = [
        group_rows
        if len(group_rows) <= reviews_per_stratum
        else randomizer.sample(group_rows, reviews_per_stratum)
        for group_rows in grouped_rows.values()
    ]
    sampled_rows = [row for group_rows in sampled_groups for row in group_rows]
    randomizer.shuffle(sampled_rows)
    return sampled_rows


class ReviewBalancer:
    """Pandas-based review sampler kept for smaller in-memory datasets."""

    INPUT_COLUMNS = ['business_id', 'name', 'category', 'stars_x', 'text', 'date']
    OUTPUT_RENAME_MAP = {
        'name': 'business_name',
        'stars_x': 'stars',
        'text': 'review_text',
        'date': 'review_date'
    }
    OUTPUT_COLUMNS = ['business_id', 'business_name', 'category', 'stars', 'review_text', 'review_date']

    def __init__(self, reviews_per_stratum=500, random_state=42):
        """
        Initialize the ReviewBalancer with the number of reviews per stratum.
        
        Args:
            reviews_per_stratum (int): Number of reviews to include per category/rating stratum
            random_state (int): Seed used for repeatable sampling
        """
        self.reviews_per_stratum = reviews_per_stratum
        self.random_state = random_state

    def _rating_group_series(self, ratings):
        """
        Convert numeric review ratings into the three required rating strata.
        """
        import pandas as pd

        return pd.cut(
            ratings,
            bins=[0, 2, 3, 5],
            labels=['1-2 stars', '3 stars', '4-5 stars'],
            include_lowest=True
        )

    @staticmethod
    def _validate_columns(df, required_columns):
        """Raise a clear error when a DataFrame is missing required columns."""
        missing_columns = [column for column in required_columns if column not in df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")

    def _sample_by_stratum(self, df):
        """
        Shuffle once and keep the first rows in each stratum, preserving undersized groups.
        """
        if df.empty:
            return df.copy()

        shuffled_df = df.sample(frac=1, random_state=self.random_state)
        return (
            shuffled_df
            .groupby(['category', '_rating_group'], sort=False, observed=True, group_keys=False)
            .head(self.reviews_per_stratum)
        )

    def _sample_group(self, group_df):
        """Return a capped random sample from a single grouped DataFrame."""
        sample_size = min(len(group_df), self.reviews_per_stratum)
        return (
            group_df
            if sample_size == len(group_df)
            else group_df.sample(n=sample_size, random_state=self.random_state)
        )

    def group_reviews(self, df):
        """
        Group reviews by category and rating.
        
        Args:
            df: DataFrame with joined review and business data
            
        Returns:
            Dictionary with category/rating groups as keys and DataFrames as values
        """
        self._validate_columns(df, ['category', 'stars_x'])

        # Add the rating stratum once, then let pandas build category/rating groups in one pass.
        grouped_df = df.assign(_rating_group=self._rating_group_series(df['stars_x']))
        grouped_df = grouped_df.dropna(subset=['category', '_rating_group'])

        return {
            key: group.drop(columns='_rating_group').copy()
            for key, group in grouped_df.groupby(['category', '_rating_group'], sort=False, observed=True)
        }

    def sample_reviews(self, grouped_reviews):
        """
        Sample reviews from each group according to the requirements.
        
        Args:
            grouped_reviews: Dictionary with category/rating groups
            
        Returns:
            Dictionary with sampled reviews
        """
        return {
            key: self._sample_group(group_df)
            for key, group_df in grouped_reviews.items()
        }

    def create_balanced_dataset(self, df):
        """
        Create a balanced dataset according to the requirements.
        
        Args:
            df: DataFrame with joined review and business data
            
        Returns:
            Balanced DataFrame with exactly the required fields
        """
        self._validate_columns(df, self.INPUT_COLUMNS)

        working_df = df[self.INPUT_COLUMNS].copy()
        working_df['_rating_group'] = self._rating_group_series(working_df['stars_x'])
        working_df = working_df.dropna(subset=['category', '_rating_group'])

        # Sampling through a single shuffle avoids full per-stratum DataFrame copies.
        balanced_df = self._sample_by_stratum(working_df)

        output_df = balanced_df.drop(columns='_rating_group')
        output_df = output_df.rename(columns=self.OUTPUT_RENAME_MAP)

        return output_df[self.OUTPUT_COLUMNS].reset_index(drop=True)

    def adjust_sample_size_if_needed(self, df, max_size_mb=30):
        """
        Adjust sample size if the output exceeds the size limit.
        
        Args:
            df: DataFrame with the balanced reviews
            max_size_mb (int): Maximum file size in MB
            
        Returns:
            Adjusted DataFrame or original if under limit
        """
        # Estimate file size (rough approximation: 1 byte per character + overhead)
        estimated_size_mb = (df.memory_usage(deep=True).sum() / (1024 * 1024)) * 1.5

        if estimated_size_mb <= max_size_mb:
            return df

        reduction_factor = max_size_mb / estimated_size_mb
        new_sample_size = max(1, int(self.reviews_per_stratum * reduction_factor))

        print(
            f"Estimated size {estimated_size_mb:.2f}MB exceeds limit. "
            f"Reducing to {new_sample_size} reviews per stratum."
        )

        self.reviews_per_stratum = new_sample_size

        if all(column in df.columns for column in self.INPUT_COLUMNS):
            return self.create_balanced_dataset(df)

        if all(column in df.columns for column in self.OUTPUT_COLUMNS):
            return self._resample_balanced_output(df)

        self._validate_columns(df, self.INPUT_COLUMNS)
        return df

    def _resample_balanced_output(self, df):
        """
        Re-sample an already balanced output DataFrame after the size limit changes.
        """
        resample_df = df[self.OUTPUT_COLUMNS].copy()
        resample_df['_rating_group'] = self._rating_group_series(resample_df['stars'])

        resampled_df = self._sample_by_stratum(resample_df.dropna(subset=['category', '_rating_group']))

        return resampled_df.drop(columns='_rating_group').reset_index(drop=True)


class ReservoirReviewBalancer:
    """
    Streaming sampler for large JSONL review files.

    This keeps at most reviews_per_stratum rows per category/rating stratum in
    memory, while still giving every eligible review an equal chance of being
    selected within its stratum.
    """

    OUTPUT_COLUMNS = ReviewBalancer.OUTPUT_COLUMNS
    RATING_GROUPS = {
        1: '1-2 stars',
        2: '1-2 stars',
        3: '3 stars',
        4: '4-5 stars',
        5: '4-5 stars',
    }

    def __init__(self, reviews_per_stratum=500, random_state=42):
        """Create a per-stratum reservoir sampler."""
        self.reviews_per_stratum = reviews_per_stratum
        self.random = random.Random(random_state)
        self.samples = defaultdict(list)
        self.seen_counts = defaultdict(int)

    @staticmethod
    def rating_group(stars):
        """Return the rating stratum label for a numeric Yelp star rating."""
        stars = int(float(stars))
        return ReservoirReviewBalancer.RATING_GROUPS.get(stars)

    def add(self, row):
        """Consider one output-shaped review row for reservoir sampling."""
        rating_group = self.rating_group(row['stars'])
        if rating_group is None:
            return

        key = (row['category'], rating_group)
        self.seen_counts[key] += 1
        seen_count = self.seen_counts[key]
        bucket = self.samples[key]

        if len(bucket) < self.reviews_per_stratum:
            bucket.append(row)
            return

        replacement_index = self.random.randrange(seen_count)
        if replacement_index < self.reviews_per_stratum:
            bucket[replacement_index] = row

    def rows(self):
        """Return sampled rows in a repeatably shuffled order."""
        output_rows = [
            row
            for key in sorted(self.samples)
            for row in self.samples[key]
        ]

        self.random.shuffle(output_rows)
        return output_rows

    def counts_by_stratum(self):
        """Return the number of eligible rows seen for each stratum."""
        return dict(self.seen_counts)
