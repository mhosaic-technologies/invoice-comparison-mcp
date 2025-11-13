"""
Utility functions and constants for invoice comparison
"""

from typing import Optional
import pandas as pd


# Match status constants
class MatchStatus:
    """Constants for match status values"""
    EXACT_MATCH = "exact_match"
    FUZZY_MATCH = "fuzzy_match"
    LOW_CONFIDENCE = "low_confidence"
    NO_MATCH = "no_match"


# Match type constants (for display)
class MatchType:
    """Constants for match type display values"""
    EXACT_MATCH = "Exact Match"
    FUZZY_MATCH = "Fuzzy Match"
    LOW_CONFIDENCE = "Low Confidence"
    NO_MATCH = "No Match"


def match_status_to_display(status: str) -> str:
    """
    Convert match status to display string

    Args:
        status: Match status constant from MatchStatus

    Returns:
        Display string from MatchType
    """
    mapping = {
        MatchStatus.EXACT_MATCH: MatchType.EXACT_MATCH,
        MatchStatus.FUZZY_MATCH: MatchType.FUZZY_MATCH,
        MatchStatus.LOW_CONFIDENCE: MatchType.LOW_CONFIDENCE,
        MatchStatus.NO_MATCH: MatchType.NO_MATCH,
    }
    return mapping.get(status, status)


def normalize_gtin(gtin_value) -> Optional[str]:
    """
    Normalize GTIN from Excel/CSV/string input

    Handles:
    - Excel floats (12345.0 -> "12345")
    - String representations ("12345.0" -> "12345")
    - Leading zeros preservation (when provided as string)
    - Validation of numeric format and length

    Args:
        gtin_value: Raw GTIN value (could be float, int, or string)

    Returns:
        Normalized GTIN string or None if invalid

    Examples:
        >>> normalize_gtin(1234567890123.0)
        '1234567890123'
        >>> normalize_gtin("1234567890123.0")
        '1234567890123'
        >>> normalize_gtin("00012345678901")
        '00012345678901'
        >>> normalize_gtin("abc123")
        None
        >>> normalize_gtin(None)
        None
    """
    # Check for missing/null values
    if pd.isna(gtin_value):
        return None

    # Convert to string and strip whitespace
    gtin_str = str(gtin_value).strip()

    # Check for string representations of null
    if gtin_str.lower() in ['nan', 'none', '']:
        return None

    # Handle float strings (e.g., "12345.0" or Excel floats)
    if '.' in gtin_str:
        # Split on decimal to preserve the integer part as-is
        integer_part = gtin_str.split('.')[0]

        # Check if integer part is already a valid GTIN length
        if integer_part.isdigit() and len(integer_part) in [8, 12, 13, 14]:
            # Preserve leading zeros from the original string
            gtin_str = integer_part
        else:
            # Try float conversion for cases like "1234567890123.0" -> "1234567890123"
            try:
                float_val = float(gtin_str)
                gtin_str = str(int(float_val))
            except (ValueError, TypeError):
                # If conversion fails, GTIN contains non-numeric characters
                print(f"Warning: Invalid GTIN '{gtin_str}' - contains non-numeric characters, skipping")
                return None

    # Validate GTIN is numeric
    if not gtin_str.isdigit():
        print(f"Warning: Invalid GTIN '{gtin_str}' - not numeric, skipping")
        return None

    # Validate GTIN length (must be 8, 12, 13, or 14 digits)
    if len(gtin_str) not in [8, 12, 13, 14]:
        print(f"Warning: Invalid GTIN length '{gtin_str}' ({len(gtin_str)} digits) - must be 8, 12, 13, or 14 digits, skipping")
        return None

    return gtin_str
