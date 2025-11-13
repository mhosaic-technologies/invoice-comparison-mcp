"""Database module"""

from .schema import (
    Product, Supplier, SupplierCode,
    UserCorrection, ComparisonHistory,
    MatchingCache, init_database, get_session
)
from .operations import DatabaseOperations

__all__ = [
    'Product', 'Supplier', 'SupplierCode',
    'UserCorrection', 'ComparisonHistory', 'MatchingCache',
    'init_database', 'get_session', 'DatabaseOperations'
]
