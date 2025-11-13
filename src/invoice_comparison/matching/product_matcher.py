"""
Unified product matching system combining GTIN and fuzzy matching
"""

import os
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from invoice_comparison.database.operations import DatabaseOperations
from invoice_comparison.database.schema import Product, Supplier, SupplierCode
from .similarity_scorer import SimilarityScorer, SimilarityScore
from rapidfuzz import fuzz


@dataclass
class MatchResult:
    """Container for a single match result"""
    product: Product
    similarity_score: float
    match_type: str  # 'gtin', 'exact', 'fuzzy', 'user_correction'
    supplier_code: Optional[str] = None
    price: Optional[float] = None
    brand_score: float = 0.0
    product_type_score: float = 0.0
    format_score: float = 0.0
    packaging_score: float = 0.0

    def __repr__(self):
        return f"MatchResult(product='{self.product.product_name[:40]}', score={self.similarity_score:.1f}%, type={self.match_type})"


class ProductMatcher:
    """
    Unified matching system that tries multiple strategies:
    1. GTIN exact match
    2. User corrections
    3. Fuzzy name matching
    """

    def __init__(self, db_path=None):
        if db_path is None:
            # Auto-detect database path relative to project root
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(os.path.dirname(current_dir))
            db_path = os.path.join(project_root, "data", "supplier_mappings.db")

        self.db_ops = DatabaseOperations(db_path)
        self.scorer = SimilarityScorer()

    def find_matches(
        self,
        product_info: Dict,
        source_supplier: str,
        target_supplier: str,
        min_similarity: float = 70.0,
        max_results: int = 5
    ) -> List[MatchResult]:
        """
        Find matching products using all available strategies

        Args:
            product_info: Dict with:
                - supplier_code: str (optional)
                - product_name: str
                - brand: str (optional)
                - format: str (optional)
                - packaging: str (optional)
            source_supplier: Source supplier code
            target_supplier: Target supplier code
            min_similarity: Minimum similarity threshold
            max_results: Maximum results to return

        Returns:
            List of MatchResult objects sorted by score
        """
        results = []

        # Strategy 1: GTIN match via supplier code
        if 'supplier_code' in product_info:
            gtin_match = self._try_gtin_match(
                product_info['supplier_code'],
                source_supplier,
                target_supplier
            )
            if gtin_match:
                results.append(gtin_match)
                return results  # GTIN match is 100% - return immediately

        # Strategy 2: User corrections
        if 'supplier_code' in product_info:
            correction_matches = self._try_user_corrections(
                product_info['supplier_code'],
                source_supplier,
                target_supplier
            )
            results.extend(correction_matches)

        # Strategy 3: Fuzzy matching
        fuzzy_matches = self._try_fuzzy_match(
            product_info,
            target_supplier,
            min_similarity,
            max_results
        )
        results.extend(fuzzy_matches)

        # Remove duplicates (by product ID)
        seen_ids = set()
        unique_results = []
        for result in results:
            if result.product.id not in seen_ids:
                seen_ids.add(result.product.id)
                unique_results.append(result)

        # Sort by similarity score
        unique_results.sort(key=lambda x: x.similarity_score, reverse=True)

        return unique_results[:max_results]

    def _try_gtin_match(
        self,
        supplier_code: str,
        source_supplier: str,
        target_supplier: str
    ) -> Optional[MatchResult]:
        """Try to find exact match via GTIN"""
        # Find product at source
        result = self.db_ops.find_product_by_supplier_code(supplier_code, source_supplier)
        if not result:
            return None

        product, _ = result

        # Find at target
        target_mapping = self.db_ops.get_supplier_code_for_product(product.id, target_supplier)
        if not target_mapping:
            return None

        return MatchResult(
            product=product,
            similarity_score=100.0,
            match_type='gtin',
            supplier_code=target_mapping.supplier_code,
            price=target_mapping.price
        )

    def _try_user_corrections(
        self,
        supplier_code: str,
        source_supplier: str,
        target_supplier: str
    ) -> List[MatchResult]:
        """Check user corrections database"""
        corrections = self.db_ops.get_user_corrections(supplier_code, source_supplier)

        results = []
        for correction in corrections:
            # Get the corrected product
            session = self.db_ops.get_session()
            try:
                product = session.query(Product).filter_by(
                    id=correction.matched_product_id
                ).first()

                if product:
                    # Get target supplier code (pass session to avoid nested sessions)
                    target_mapping = self.db_ops.get_supplier_code_for_product(
                        product.id,
                        target_supplier,
                        session=session
                    )

                    if target_mapping:
                        results.append(MatchResult(
                            product=product,
                            similarity_score=95.0,  # High score for user-confirmed matches
                            match_type='user_correction',
                            supplier_code=target_mapping.supplier_code,
                            price=target_mapping.price
                        ))
            finally:
                # Explicitly detach objects before closing session
                # This allows returned Product objects to be used after session closes
                session.expunge_all()
                session.close()

        return results

    def _try_fuzzy_match(
        self,
        product_info: Dict,
        target_supplier: str,
        min_similarity: float,
        max_results: int
    ) -> List[MatchResult]:
        """Try fuzzy matching"""
        # Get all products at target supplier
        session = self.db_ops.get_session()
        try:
            supplier = session.query(Supplier).filter_by(code=target_supplier).first()
            if not supplier:
                return []

            # Get products available at target supplier
            query = session.query(Product, SupplierCode).join(SupplierCode).filter(
                SupplierCode.supplier_id == supplier.id,
                SupplierCode.active == True
            )

            # Limit to reasonable number for performance
            products_with_codes = query.limit(10000).all()

            results = []
            search_product = {
                'product_name': product_info.get('product_name', ''),
                'brand': product_info.get('brand', ''),
                'format': product_info.get('format', ''),
                'packaging': product_info.get('packaging', '')
            }

            for product, supplier_code_obj in products_with_codes:
                target_product = {
                    'product_name': product.product_name or '',
                    'brand': product.brand or '',
                    'format': product.format or '',
                    'packaging': product.packaging or ''
                }

                similarity = self.scorer.calculate_similarity(search_product, target_product)

                if similarity.total_score >= min_similarity:
                    results.append(MatchResult(
                        product=product,
                        similarity_score=similarity.total_score,
                        match_type='fuzzy',
                        supplier_code=supplier_code_obj.supplier_code,
                        price=supplier_code_obj.price,
                        brand_score=similarity.brand_score,
                        product_type_score=similarity.product_type_score,
                        format_score=similarity.format_score,
                        packaging_score=similarity.packaging_score
                    ))

            # Sort by score
            results.sort(key=lambda x: x.similarity_score, reverse=True)

            return results[:max_results]

        finally:
            # Explicitly detach objects before closing session
            # This allows returned Product objects to be used after session closes
            session.expunge_all()
            session.close()


if __name__ == "__main__":
    print("=== Testing Product Matcher ===\n")

    matcher = ProductMatcher()

    # Test products from invoice
    test_products = [
        {
            'supplier_code': '325141',
            'product_name': 'YOGOURT VANILLE 1.5% ORIG IOGO',
            'brand': 'IOGO',
            'format': '4X2 KG',
            'packaging': ''
        },
        {
            'supplier_code': '162609',
            'product_name': 'TOFU FERME BIO SOUS VIDE',
            'brand': '',
            'format': '12X454 G',
            'packaging': ''
        },
        {
            'supplier_code': '238533',
            'product_name': 'CEREALE CHEERIOS VRAC',
            'brand': 'CHEERIOS',
            'format': '4X822 G',
            'packaging': ''
        }
    ]

    for i, product in enumerate(test_products, 1):
        print(f"{i}. Product: {product['product_name']}")
        print(f"   Dubé Loiselle Code: {product['supplier_code']}")
        print(f"   Format: {product['format']}\n")

        matches = matcher.find_matches(
            product,
            source_supplier="dube_loiselle",
            target_supplier="colabor",
            min_similarity=60.0,
            max_results=3
        )

        if matches:
            print(f"   Found {len(matches)} matches at Colabor:")
            for j, match in enumerate(matches, 1):
                print(f"\n   {j}. [{match.similarity_score:.1f}% - {match.match_type}] {match.product.product_name}")
                print(f"      Brand: {match.product.brand or 'N/A'}")
                print(f"      Format: {match.product.format or 'N/A'}")
                if match.supplier_code:
                    print(f"      Colabor Code: {match.supplier_code}")
                if match.match_type == 'fuzzy':
                    print(f"      Detail: Brand={match.brand_score:.0f}% Product={match.product_type_score:.0f}% Format={match.format_score:.0f}%")
        else:
            print("   No matches found")

        print("\n" + "-" * 80 + "\n")

    print("=== Test Complete ===")
