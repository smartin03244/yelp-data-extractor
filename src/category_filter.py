"""Category mapping utilities for Yelp business records."""

import re

import pandas as pd


class CategoryFilter:
    """Map raw Yelp business categories into simplified project categories."""

    CATEGORY_MAPPINGS = {
        'Restaurants': (
            'restaurant', 'food', 'pizza', 'burger', 'sandwich', 'tacos',
            'sushi', 'bar', 'pub', 'breakfast', 'brunch', 'diner', 'cafe',
            'bistro', 'steakhouse', 'seafood', 'bbq', 'italian', 'mexican',
            'chinese', 'japanese', 'thai', 'indian', 'french', 'greek'
        ),
        'Hair Salons & Barber Shops': ('hair', 'salon', 'barber', 'hairstyle'),
        'Nail Salons': ('nail', 'manicure', 'pedicure'),
        'Spas & Massage': ('spa', 'massage', 'wellness'),
        'Auto Repair & Service': ('auto', 'car', 'repair', 'automotive', 'garage'),
        'Hotels & Lodging': ('hotel', 'lodging', 'motel', 'inn', 'resort'),
        'Dental & Medical Offices': ('dental', 'dentist', 'medical', 'doctor', 'health'),
        'Gyms & Fitness': ('gym', 'fitness', 'yoga', 'pilates', 'workout'),
        'Tours & Experiences': ('tour', 'tourism', 'attraction'),
        'Retail / Boutique': ('retail', 'shop', 'store', 'boutique', 'shopping'),
    }
    TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

    def __init__(self):
        """Precompute keyword sets for efficient category matching."""
        self.keywords_by_category = {
            category: set(keywords)
            for category, keywords in self.CATEGORY_MAPPINGS.items()
        }

    def _iter_category_tokens(self, categories):
        """Yield normalized category tokens, including simple singular forms."""
        if categories is None or categories is pd.NA:
            return

        if isinstance(categories, str):
            text = categories
        else:
            try:
                text = ' '.join(str(category) for category in categories if pd.notna(category))
            except TypeError:
                text = str(categories)

        for token in self.TOKEN_PATTERN.findall(text.lower()):
            yield token

            if len(token) > 3 and token.endswith('s'):
                yield token[:-1]

    def categorize_business(self, categories_list):
        """Map a business's raw Yelp categories to a simplified category.
        
        Args:
            categories_list: List of category strings from the business data
            
        Returns:
            String with simplified category or None if no match
        """
        tokens = set(self._iter_category_tokens(categories_list))

        for category, keywords in self.keywords_by_category.items():
            if any(keyword in tokens for keyword in keywords):
                return category

        return None
    
    def filter_by_category(self, df):
        """
        Filter the DataFrame to include only businesses in our target categories.
        
        Args:
            df: DataFrame with business data
            
        Returns:
            Filtered DataFrame with only target businesses and a new 'category' column
        """
        if 'categories' not in df.columns:
            raise ValueError("Missing required column: categories")

        categories = df['categories'].map(self.categorize_business)
        filtered_df = df.loc[categories.notna()].copy()
        filtered_df['category'] = categories.loc[filtered_df.index]

        return filtered_df
    
    def get_category_distribution(self, df):
        """
        Get the distribution of businesses across categories.
        
        Args:
            df: DataFrame with business data including 'category' column
            
        Returns:
            Series with counts per category
        """
        if 'category' not in df.columns:
            raise ValueError("Missing required column: category")

        return df['category'].value_counts()
