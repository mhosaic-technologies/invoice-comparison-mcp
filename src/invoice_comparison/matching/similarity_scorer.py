"""
Similarity scoring algorithms for product matching
"""

import re
from typing import Dict, Tuple
from rapidfuzz import fuzz
from dataclasses import dataclass


@dataclass
class SimilarityScore:
    """Container for similarity scores"""
    total_score: float
    brand_score: float
    product_type_score: float
    format_score: float
    packaging_score: float

    def __repr__(self):
        return f"SimilarityScore(total={self.total_score:.2f}%, brand={self.brand_score:.0f}%, product={self.product_type_score:.0f}%, format={self.format_score:.0f}%, pkg={self.packaging_score:.0f}%)"


class SimilarityScorer:
    """
    Calculate weighted similarity scores between products

    Weights:
    - Brand name: 25%
    - Product type: 40%
    - Format/size: 25%
    - Packaging: 10%
    """

    # Weights for different components
    WEIGHTS = {
        'brand': 0.25,
        'product_type': 0.40,
        'format': 0.25,
        'packaging': 0.10
    }

    # Common brand synonyms
    BRAND_SYNONYMS = {
        'olimel': ['olymel'],
        'maple leaf': ['maple', 'mapleleaf'],
        'coca cola': ['coca-cola', 'coke'],
        'pepsi': ['pepsi-cola'],
    }

    # Format conversion patterns
    # Each pattern has two capture groups: count and size
    # Second group is optional to handle simple formats like "2kg" or "500g"
    FORMAT_PATTERNS = {
        'kg': r'(\d+(?:\.\d+)?)\s*(?:x\s*)?(\d+(?:\.\d+)?)?\s*(?:kg|kilo|kilogram)',
        'g': r'(\d+(?:\.\d+)?)\s*(?:x\s*)?(\d+(?:\.\d+)?)?\s*(?:g|gram)',
        'l': r'(\d+(?:\.\d+)?)\s*(?:x\s*)?(\d+(?:\.\d+)?)?\s*(?:l|liter|litre)',
        'ml': r'(\d+(?:\.\d+)?)\s*(?:x\s*)?(\d+(?:\.\d+)?)?\s*(?:ml|milliliter)',
        'units': r'(\d+)\s*(?:x\s*)?(\d+)?\s*(?:un|unit|piece|pce)',
    }

    def __init__(self):
        """Initialize the similarity scorer"""
        pass

    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison"""
        if not text:
            return ""

        # Convert to lowercase
        text = text.lower().strip()

        # Remove special characters but keep spaces and numbers
        text = re.sub(r'[^\w\s\.]', ' ', text)

        # Remove extra spaces
        text = re.sub(r'\s+', ' ', text)

        return text

    def extract_brand(self, product_name: str, brand_field: str = None) -> str:
        """Extract brand name from product description or brand field"""
        if brand_field and brand_field.strip():
            return self.normalize_text(brand_field)

        # Try to extract from product name
        # Brands are often at the end or in caps
        normalized = self.normalize_text(product_name)

        # Common brand patterns
        words = normalized.split()
        if len(words) > 0:
            # Last word is often the brand
            return words[-1]

        return ""

    def extract_product_type(self, product_name: str) -> str:
        """Extract product type (e.g., 'yogurt', 'cheese', 'chicken')"""
        normalized = self.normalize_text(product_name)

        # Remove brand, format, and common descriptors
        # Keep the main product type words
        words = normalized.split()

        # Filter out numbers and units
        product_words = []
        for word in words:
            if not re.match(r'^\d+', word) and len(word) > 2:
                # Skip common descriptors
                if word not in ['bio', 'organic', 'naturel', 'nature', 'original', 'orig']:
                    product_words.append(word)

        # Return first 3 words as product type
        return ' '.join(product_words[:3])

    def extract_format(self, format_field: str, product_name: str = "") -> Tuple[float, str]:
        """
        Extract and normalize format/size

        Returns:
            (total_quantity_in_grams, unit_type)
        """
        text = self.normalize_text(f"{format_field} {product_name}")

        # Try to find quantity patterns
        for unit_type, pattern in self.FORMAT_PATTERNS.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    groups = match.groups()

                    # Handle different group patterns
                    if len(groups) >= 2 and groups[0]:
                        if groups[1]:
                            # e.g., "4 x 2 kg" -> count=4, size=2
                            count = float(groups[0])
                            size = float(groups[1])
                        else:
                            # e.g., "2 kg" -> count=1, size=2
                            count = 1
                            size = float(groups[0])
                    else:
                        # Should not reach here with current patterns
                        continue

                    # Convert to grams
                    if unit_type == 'kg':
                        total_grams = count * size * 1000
                    elif unit_type == 'g':
                        total_grams = count * size
                    elif unit_type == 'l':
                        total_grams = count * size * 1000  # Approximate for liquids
                    elif unit_type == 'ml':
                        total_grams = count * size
                    else:  # units
                        total_grams = count * (size if size else 1)

                    return (total_grams, unit_type)
                except (ValueError, TypeError):
                    # If conversion fails, continue to next pattern
                    continue

        return (0.0, "unknown")

    def compare_formats(self, format1: str, format2: str, name1: str = "", name2: str = "") -> float:
        """
        Compare format similarity

        Returns similarity score 0-100
        """
        qty1, unit1 = self.extract_format(format1, name1)
        qty2, unit2 = self.extract_format(format2, name2)

        if qty1 == 0 or qty2 == 0:
            # Fall back to string similarity
            norm1 = self.normalize_text(format1)
            norm2 = self.normalize_text(format2)

            # If both are empty, we have no information - return neutral score
            if not norm1 and not norm2:
                return 50.0

            return fuzz.ratio(norm1, norm2)

        # Calculate percentage difference
        diff_percent = abs(qty1 - qty2) / max(qty1, qty2) * 100

        # Convert to similarity (100% diff = 0 similarity, 0% diff = 100 similarity)
        similarity = max(0, 100 - diff_percent)

        # Bonus if same unit type
        if unit1 == unit2:
            similarity = min(100, similarity * 1.1)

        return similarity

    def extract_packaging(self, packaging_field: str, product_name: str = "") -> str:
        """Extract packaging type"""
        text = self.normalize_text(f"{packaging_field} {product_name}")

        # Common packaging types
        packaging_types = ['box', 'boite', 'case', 'caisse', 'bag', 'sac', 'bottle', 'bouteille',
                          'can', 'canne', 'jar', 'pot', 'tray', 'plateau']

        for pkg in packaging_types:
            if pkg in text:
                return pkg

        return "unknown"

    def compare_brands(self, brand1: str, brand2: str) -> float:
        """Compare brand names with synonym support"""
        b1 = self.normalize_text(brand1)
        b2 = self.normalize_text(brand2)

        # If both are empty, we have no information - return neutral score
        if not b1 and not b2:
            return 50.0

        # If only one is empty, we can't compare - return 0
        if not b1 or not b2:
            return 0.0

        # Check for exact match
        if b1 == b2:
            return 100.0

        # Check synonyms
        for canonical, synonyms in self.BRAND_SYNONYMS.items():
            if b1 in synonyms and b2 == canonical:
                return 95.0
            if b2 in synonyms and b1 == canonical:
                return 95.0
            if b1 in synonyms and b2 in synonyms:
                return 95.0

        # Use fuzzy matching
        return fuzz.ratio(b1, b2)

    def calculate_similarity(
        self,
        product1: Dict,
        product2: Dict
    ) -> SimilarityScore:
        """
        Calculate weighted similarity between two products

        Args:
            product1: Dict with keys: product_name, brand, format, packaging
            product2: Dict with keys: product_name, brand, format, packaging

        Returns:
            SimilarityScore object with detailed scores
        """
        # Extract fields
        name1 = product1.get('product_name', '')
        name2 = product2.get('product_name', '')
        brand1 = product1.get('brand', '')
        brand2 = product2.get('brand', '')
        format1 = product1.get('format', '')
        format2 = product2.get('format', '')
        pkg1 = product1.get('packaging', '')
        pkg2 = product2.get('packaging', '')

        # Calculate individual scores
        brand_score = self.compare_brands(brand1, brand2)

        # Product type comparison
        type1 = self.extract_product_type(name1)
        type2 = self.extract_product_type(name2)

        # If both are empty, we have no information - return neutral score
        if not type1 and not type2:
            product_type_score = 50.0
        else:
            product_type_score = fuzz.token_sort_ratio(type1, type2)

        # Format comparison
        format_score = self.compare_formats(format1, format2, name1, name2)

        # Packaging comparison
        pkg_type1 = self.extract_packaging(pkg1, name1)
        pkg_type2 = self.extract_packaging(pkg2, name2)

        # If both are unknown, we have no information - return neutral score
        if pkg_type1 == "unknown" and pkg_type2 == "unknown":
            packaging_score = 50.0
        elif pkg_type1 == pkg_type2:
            packaging_score = 100.0
        else:
            packaging_score = fuzz.ratio(pkg_type1, pkg_type2)

        # Calculate weighted total
        total_score = (
            brand_score * self.WEIGHTS['brand'] +
            product_type_score * self.WEIGHTS['product_type'] +
            format_score * self.WEIGHTS['format'] +
            packaging_score * self.WEIGHTS['packaging']
        )

        return SimilarityScore(
            total_score=total_score,
            brand_score=brand_score,
            product_type_score=product_type_score,
            format_score=format_score,
            packaging_score=packaging_score
        )


if __name__ == "__main__":
    # Test the scorer
    scorer = SimilarityScorer()

    # Test products
    product1 = {
        'product_name': 'YOGOURT VANILLE 1.5% ORIG IOGO',
        'brand': 'IOGO',
        'format': '4X2 KG',
        'packaging': 'CASE'
    }

    product2 = {
        'product_name': 'YOGOURT VANILLE IOGO',
        'brand': 'IOGO',
        'format': '4X2KG',
        'packaging': 'BOX'
    }

    product3 = {
        'product_name': 'YOGOURT FRAISE IOGO',
        'brand': 'IOGO',
        'format': '4X2.5 KG',
        'packaging': 'CASE'
    }

    print("=== Testing Similarity Scorer ===\n")

    score1 = scorer.calculate_similarity(product1, product2)
    print(f"Product 1 vs Product 2 (very similar):")
    print(f"  {score1}")
    print(f"  Total: {score1.total_score:.1f}%\n")

    score2 = scorer.calculate_similarity(product1, product3)
    print(f"Product 1 vs Product 3 (different flavor/size):")
    print(f"  {score2}")
    print(f"  Total: {score2.total_score:.1f}%\n")
