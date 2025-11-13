"""
GTIN-based exact matching
"""

from typing import Optional, List, Tuple
from invoice_comparison.database.operations import DatabaseOperations
from invoice_comparison.database.schema import Product, SupplierCode


class GTINMatcher:
    """Handle GTIN-based exact matching"""

    def __init__(self, db_path="data/supplier_mappings.db"):
        self.db_ops = DatabaseOperations(db_path)

    def find_by_gtin(self, gtin: str) -> Optional[Product]:
        """
        Find product by GTIN code

        Args:
            gtin: GTIN/UPC code

        Returns:
            Product if found, None otherwise
        """
        return self.db_ops.find_product_by_gtin(gtin)

    def find_by_supplier_code(
        self,
        supplier_code: str,
        supplier: str
    ) -> Optional[Tuple[Product, SupplierCode]]:
        """
        Find product by supplier-specific code

        Args:
            supplier_code: Supplier's product code
            supplier: Supplier identifier (e.g., 'colabor')

        Returns:
            Tuple of (Product, SupplierCode) if found
        """
        return self.db_ops.find_product_by_supplier_code(supplier_code, supplier)

    def find_cross_supplier_match(
        self,
        supplier_code: str,
        source_supplier: str,
        target_supplier: str
    ) -> Optional[Tuple[Product, SupplierCode]]:
        """
        Find equivalent product at target supplier

        Args:
            supplier_code: Product code at source supplier
            source_supplier: Source supplier code
            target_supplier: Target supplier code

        Returns:
            Tuple of (Product, SupplierCode at target) if found
        """
        # First, find the product at source
        result = self.find_by_supplier_code(supplier_code, source_supplier)

        if not result:
            return None

        product, _ = result

        # Now find it at target supplier
        target_mapping = self.db_ops.get_supplier_code_for_product(
            product.id,
            target_supplier
        )

        if target_mapping:
            return (product, target_mapping)

        return None

    def get_all_supplier_codes_for_product(
        self,
        product_id: int
    ) -> List[Tuple[str, SupplierCode]]:
        """
        Get all supplier codes for a product

        Args:
            product_id: Product ID

        Returns:
            List of (supplier_name, SupplierCode) tuples
        """
        session = self.db_ops.get_session()
        try:
            from database.schema import Supplier

            mappings = session.query(SupplierCode, Supplier).join(
                Supplier, SupplierCode.supplier_id == Supplier.id
            ).filter(
                SupplierCode.product_id == product_id,
                SupplierCode.active == True
            ).all()

            return [(supplier.code, mapping) for mapping, supplier in mappings]

        finally:
            session.close()


if __name__ == "__main__":
    # Test GTIN matcher
    print("=== Testing GTIN Matcher ===\n")

    matcher = GTINMatcher()

    # Test 1: Find by supplier code
    print("1. Find product by supplier code:")
    result = matcher.find_by_supplier_code("155915", "dube_loiselle")
    if result:
        product, mapping = result
        print(f"   ✓ Found: {product.product_name}")
        print(f"     GTIN: {product.gtin}")
        print(f"     Brand: {product.brand}")
        print(f"     Format: {product.format}")

        # Test 2: Find cross-supplier
        print("\n2. Find equivalent at Colabor:")
        cross = matcher.find_cross_supplier_match("155915", "dube_loiselle", "colabor")
        if cross:
            prod, target_map = cross
            print(f"   ✓ Found at Colabor")
            print(f"     Code: {target_map.supplier_code}")
        else:
            print(f"   ✗ Not available at Colabor")

        # Test 3: Get all suppliers
        print("\n3. All suppliers carrying this product:")
        all_codes = matcher.get_all_supplier_codes_for_product(product.id)
        for supplier, mapping in all_codes:
            print(f"   - {supplier:20} Code: {mapping.supplier_code}")
    else:
        print("   ✗ Product not found")

    print("\n=== Test Complete ===")
