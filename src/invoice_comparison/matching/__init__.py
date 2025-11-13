"""Matching module - Product similarity matching"""

from .similarity_scorer import SimilarityScorer
from .fuzzy_matcher import FuzzyMatcher
from .gtin_matcher import GTINMatcher
from .product_matcher import ProductMatcher

__all__ = ['SimilarityScorer', 'FuzzyMatcher', 'GTINMatcher', 'ProductMatcher']
