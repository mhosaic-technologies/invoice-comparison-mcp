"""
Fuzzy matching for products without direct GTIN matches
"""

from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from invoice_comparison.database.operations import DatabaseOperations
from invoice_comparison.database.schema import Product, Supplier, SupplierCode
from .similarity_scorer import SimilarityScorer, SimilarityScore


@dataclass
class MatchResult:
    """Container for a single match result"""
    product: Product
    similarity_score: float
    detailed_scores: SimilarityScore
    supplier_code: Optional[str] = None
    price: Optional[float] = None

    def __repr__(self):
        return f"MatchResult(product='{self.product.product_name[:40]}', score={self.similarity_score:.1f}%, code={self.supplier_code})"


class FuzzyMatcher:
    """Fuzzy matching engine for finding similar products"""

    def __init__(self, db_path="data/supplier_mappings.db"):
        self.db_ops = DatabaseOperations(db_path)
        self.scorer = SimilarityScorer()

    def search_similar_products(
        self,
        search_product: Dict,
        target_supplier: str = None,
        min_similarity: float = 50.0,
        max_results: int = 5,
        category: str = None
    ) -> List[MatchResult]:
        """
        Search for similar products using fuzzy matching

        Args:
            search_product: Dict with product info to search for
                {
                    'product_name': str,
                    'brand': str (optional),
                    'format': str (optional),
                    'packaging': str (optional)
                }
            target_supplier: Limit search to products available at this supplier
            min_similarity: Minimum similarity score (0-100)
            max_results: Maximum number of results to return
            category: Filter by category if provided

        Returns:
            List of MatchResult objects, sorted by similarity (highest first)
        """
        # Check cache first
        search_text = f"{search_product.get('product_name', '')} {search_product.get('brand', '')} {search_product.get('format', '')}"
        cached = self.db_ops.get_cached_match(search_text)

        if cached and target_supplier is None:
            product, score = cached
            detailed = self.scorer.calculate_similarity(
                search_product,
                {
                    'product_name': product.product_name,
                    'brand': product.brand or '',
                    'format': product.format or '',
                    'packaging': product.packaging or ''
                }
            )
            return [MatchResult(
                product=product,
                similarity_score=score,
                detailed_scores=detailed
            )]

        # Get all products from database
        session = self.db_ops.get_session()
        try:
            query = session.query(Product)

            # Filter by category if provided
            if category:
                query = query.filter(Product.category == category)

            # If target supplier specified, only get products available there
            if target_supplier:
                supplier = session.query(Supplier).filter_by(code=target_supplier).first()
                if supplier:
                    # Join with supplier codes
                    query = query.join(SupplierCode).filter(
                        SupplierCode.supplier_id == supplier.id,
                        SupplierCode.active == True
                    )

            # Safety limit to prevent memory exhaustion with very large databases
            # Fuzzy matching requires comparing against all products, but we limit
            # to prevent catastrophic memory usage if database grows unexpectedly
            products = query.limit(100000).all()

            # Calculate similarity for each product
            results = []
            for product in products:
                target_product = {
                    'product_name': product.product_name,
                    'brand': product.brand or '',
                    'format': product.format or '',
                    'packaging': product.packaging or ''
                }

                similarity = self.scorer.calculate_similarity(search_product, target_product)

                if similarity.total_score >= min_similarity:
                    # Get supplier code if applicable
                    supplier_code = None
                    price = None

                    if target_supplier:
                        mapping = self.db_ops.get_supplier_code_for_product(
                            product.id,
                            target_supplier
                        )
                        if mapping:
                            supplier_code = mapping.supplier_code
                            price = mapping.price

                    results.append(MatchResult(
                        product=product,
                        similarity_score=similarity.total_score,
                        detailed_scores=similarity,
                        supplier_code=supplier_code,
                        price=price
                    ))

            # Sort by similarity score (descending)
            results.sort(key=lambda x: x.similarity_score, reverse=True)

            # Limit results
            results = results[:max_results]

            # Cache the best result if high confidence
            if results and results[0].similarity_score >= 85.0 and target_supplier is None:
                self.db_ops.cache_match(
                    search_text,
                    results[0].product.id,
                    results[0].similarity_score,
                    'fuzzy_name'
                )

            return results

        finally:
            session.close()

    def find_alternatives(
        self,
        product_name: str,
        brand: str = None,
        format: str = None,
        target_supplier: str = "colabor",
        min_similarity: float = 70.0
    ) -> List[MatchResult]:
        """
        Simplified interface to find product alternatives

        Args:
            product_name: Product description
            brand: Brand name (optional)
            format: Format/size (optional)
            target_supplier: Supplier to search in
            min_similarity: Minimum similarity threshold

        Returns:
            List of top matching products
        """
        search_product = {
            'product_name': product_name,
            'brand': brand or '',
            'format': format or '',
            'packaging': ''
        }

        return self.search_similar_products(
            search_product,
            target_supplier=target_supplier,
            min_similarity=min_similarity,
            max_results=5
        )


if __name__ == "__main__":
    # Test fuzzy matcher
    print("=== Testing Fuzzy Matcher ===\n")

    matcher = FuzzyMatcher()

    # Test products from invoice
    test_products = [
        {
            'product_name': 'TOFU FERME BIO SOUS VIDE',
            'brand': 'Unknown',
            'format': '12X454 G',
            'packaging': ''
        },
        {
            'product_name': 'YOGOURT VANILLE 1.5% ORIG IOGO',
            'brand': 'IOGO',
            'format': '4X2 KG',
            'packaging': ''
        },
        {
            'product_name': 'CEREALE CHEERIOS VRAC',
            'brand': 'CHEERIOS',
            'format': '4X822 G',
            'packaging': ''
        }
    ]

    for i, product in enumerate(test_products, 1):
        print(f"{i}. Searching for: {product['product_name']}")
        print(f"   Brand: {product['brand']}, Format: {product['format']}")

        matches = matcher.search_similar_products(
            product,
            target_supplier="colabor",
            min_similarity=60.0,
            max_results=3
        )

        if matches:
            print(f"   Found {len(matches)} matches:")
            for j, match in enumerate(matches, 1):
                print(f"   {j}. [{match.similarity_score:.1f}%] {match.product.product_name[:50]}")
                print(f"      Brand: {match.product.brand}, Format: {match.product.format}")
                if match.supplier_code:
                    print(f"      Colabor Code: {match.supplier_code}")
                print(f"      Scores: {match.detailed_scores}")
        else:
            print("   No matches found")

        print()

    print("=== Test Complete ===")
