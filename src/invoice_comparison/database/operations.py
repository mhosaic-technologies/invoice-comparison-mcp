"""
Database operations for managing products and suppliers
"""

import pandas as pd
import hashlib
from datetime import datetime
from typing import List, Optional, Dict, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from .schema import (
    Product, Supplier, SupplierCode, UserCorrection,
    ComparisonHistory, MatchingCache, get_session
)
from invoice_comparison.utils import normalize_gtin


class DatabaseOperations:
    """Handle all database operations"""

    def __init__(self, db_path="data/supplier_mappings.db"):
        self.db_path = db_path

    def get_session(self) -> Session:
        """Get a new database session"""
        return get_session(self.db_path)

    def load_master_gtin(self, excel_path: str = "master_GTIN.xlsx") -> Dict[str, int]:
        """
        Load master GTIN file into database

        Args:
            excel_path: Path to master GTIN Excel file

        Returns:
            Dict with counts of loaded products and mappings
        """
        print(f"Loading master GTIN data from {excel_path}...")

        # Read Excel
        df = pd.read_excel(excel_path)

        # Validate required columns exist
        required_columns = ['GTIN']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {', '.join(missing_columns)}. "
                           f"Available columns: {', '.join(df.columns)}")

        session = self.get_session()
        stats = {
            "products_added": 0,
            "products_updated": 0,
            "mappings_added": 0,
            "mappings_updated": 0,
        }

        # Get or create suppliers
        supplier_map = {
            "Code Colabor": "colabor",
            "Code Mayrand": "mayrand",
            "Code FLB": "flb",
            "Code Ben Deshaies": "ben_deshaies",
            "Code Dubé Loiselle": "dube_loiselle",
        }

        # Pre-load all suppliers to avoid N+1 query problem
        # Query once instead of querying inside the loop for every row
        supplier_objects = {}
        for supplier_code in supplier_map.values():
            supplier_obj = session.query(Supplier).filter_by(code=supplier_code).first()
            if supplier_obj:
                supplier_objects[supplier_code] = supplier_obj
            else:
                print(f"Warning: Supplier {supplier_code} not found in database")

        try:
            for idx, row in df.iterrows():
                # Normalize GTIN (handles Excel floats and validates format)
                gtin = normalize_gtin(row['GTIN'])
                if not gtin:
                    continue

                # Check if product exists
                product = session.query(Product).filter_by(gtin=gtin).first()

                if not product:
                    # Create new product
                    product = Product(
                        gtin=gtin,
                        product_name=str(row.get('Produit ', '')).strip() if pd.notna(row.get('Produit ')) else 'Unknown',
                        brand=str(row.get('Marque ', '')).strip() if pd.notna(row.get('Marque ')) else None,
                        format=str(row.get('Format', '')).strip() if pd.notna(row.get('Format')) else None,
                        packaging=str(row.get('Empaquetage ', '')).strip() if pd.notna(row.get('Empaquetage ')) else None,
                        aliments_quebec=str(row.get('Aliments du Québec', '')).strip() if pd.notna(row.get('Aliments du Québec')) else None,
                    )
                    session.add(product)
                    session.flush()  # Get the product ID
                    stats["products_added"] += 1
                else:
                    # Update existing product only if data actually changed
                    updated = False

                    new_product_name = str(row.get('Produit ', '')).strip() if pd.notna(row.get('Produit ')) else None
                    if new_product_name and product.product_name != new_product_name:
                        product.product_name = new_product_name
                        updated = True

                    new_brand = str(row.get('Marque ', '')).strip() if pd.notna(row.get('Marque ')) else None
                    if new_brand and product.brand != new_brand:
                        product.brand = new_brand
                        updated = True

                    new_format = str(row.get('Format', '')).strip() if pd.notna(row.get('Format')) else None
                    if new_format and product.format != new_format:
                        product.format = new_format
                        updated = True

                    new_packaging = str(row.get('Empaquetage ', '')).strip() if pd.notna(row.get('Empaquetage ')) else None
                    if new_packaging and product.packaging != new_packaging:
                        product.packaging = new_packaging
                        updated = True

                    if updated:
                        product.updated_at = datetime.utcnow()
                        stats["products_updated"] += 1

                # Add supplier codes
                for excel_col, supplier_code in supplier_map.items():
                    supplier_product_code = row.get(excel_col)

                    if pd.notna(supplier_product_code):
                        # Get supplier from pre-loaded cache (avoids N+1 query problem)
                        supplier = supplier_objects.get(supplier_code)
                        if not supplier:
                            # Already warned during pre-load, skip silently
                            continue

                        # Normalize supplier product code
                        # Handle both numeric codes (from Excel as float) and alphanumeric codes
                        try:
                            # Try to convert to int first (handles Excel numbers like 123.0)
                            code_str = str(int(float(supplier_product_code)))
                        except (ValueError, TypeError):
                            # If conversion fails, use as string (handles alphanumeric codes)
                            code_str = str(supplier_product_code).strip()

                        # Check if mapping exists
                        existing = session.query(SupplierCode).filter(
                            and_(
                                SupplierCode.supplier_id == supplier.id,
                                SupplierCode.supplier_code == code_str
                            )
                        ).first()

                        if not existing:
                            # Create new mapping
                            mapping = SupplierCode(
                                supplier_id=supplier.id,
                                product_id=product.id,
                                supplier_code=code_str,
                            )
                            session.add(mapping)
                            stats["mappings_added"] += 1
                        else:
                            # Update existing
                            existing.product_id = product.id
                            existing.active = True
                            existing.updated_at = datetime.utcnow()
                            stats["mappings_updated"] += 1

                # Commit every 1000 rows
                if idx % 1000 == 0:
                    session.commit()
                    print(f"  Processed {idx} rows...")

            # Final commit
            session.commit()
            print("\n✓ Master GTIN data loaded successfully!")
            print(f"  Products added: {stats['products_added']}")
            print(f"  Products updated: {stats['products_updated']}")
            print(f"  Mappings added: {stats['mappings_added']}")
            print(f"  Mappings updated: {stats['mappings_updated']}")

        except Exception as e:
            session.rollback()
            print(f"Error loading data: {e}")
            raise
        finally:
            session.close()

        return stats

    def find_product_by_gtin(self, gtin: str) -> Optional[Product]:
        """Find product by GTIN code"""
        session = self.get_session()
        try:
            result = session.query(Product).filter_by(gtin=gtin).first()
            return result
        finally:
            # Explicitly detach objects before closing session
            session.expunge_all()
            session.close()

    def find_product_by_supplier_code(self, supplier_code: str, supplier: str, session: Session = None) -> Optional[Tuple[Product, SupplierCode]]:
        """
        Find product by supplier-specific code

        Args:
            supplier_code: Supplier's product code
            supplier: Supplier code (e.g., 'colabor')
            session: Optional existing session to use (if None, creates new session)

        Returns:
            Tuple of (Product, SupplierCode) if found
        """
        # Use provided session or create a new one
        session_provided = session is not None
        if not session_provided:
            session = self.get_session()

        try:
            supplier_obj = session.query(Supplier).filter_by(code=supplier).first()
            if not supplier_obj:
                return None

            mapping = session.query(SupplierCode).filter(
                and_(
                    SupplierCode.supplier_id == supplier_obj.id,
                    SupplierCode.supplier_code == str(supplier_code),
                    SupplierCode.active == True
                )
            ).first()

            if mapping:
                result = (mapping.product, mapping)
            else:
                result = None
            return result
        finally:
            # Only close session if we created it (not if it was provided)
            if not session_provided:
                session.expunge_all()
                session.close()

    def get_supplier_code_for_product(self, product_id: int, supplier: str, session: Session = None) -> Optional[SupplierCode]:
        """
        Get supplier code for a product

        Args:
            product_id: Product ID
            supplier: Supplier code
            session: Optional existing session to use (if None, creates new session)

        Returns:
            SupplierCode if found
        """
        # Use provided session or create a new one
        session_provided = session is not None
        if not session_provided:
            session = self.get_session()

        try:
            supplier_obj = session.query(Supplier).filter_by(code=supplier).first()
            if not supplier_obj:
                return None

            result = session.query(SupplierCode).filter(
                and_(
                    SupplierCode.product_id == product_id,
                    SupplierCode.supplier_id == supplier_obj.id,
                    SupplierCode.active == True
                )
            ).first()
            return result
        finally:
            # Only close session if we created it (not if it was provided)
            if not session_provided:
                session.expunge_all()
                session.close()

    def add_user_correction(self, correction_data: Dict, session: Session = None) -> UserCorrection:
        """
        Save a user correction for learning (prevents duplicates)

        Args:
            correction_data: Dict with correction details
            session: Optional existing session to use (if None, creates new session)

        Returns:
            Created or existing UserCorrection object
        """
        # Use provided session or create a new one
        session_provided = session is not None
        if not session_provided:
            session = self.get_session()

        try:
            # Check if this exact correction already exists to prevent duplicates
            existing = session.query(UserCorrection).filter(
                and_(
                    UserCorrection.original_supplier_id == correction_data['original_supplier_id'],
                    UserCorrection.original_supplier_code == correction_data['original_supplier_code'],
                    UserCorrection.matched_product_id == correction_data['matched_product_id'],
                    UserCorrection.target_supplier_id == correction_data['target_supplier_id'],
                    UserCorrection.user_confirmed == True
                )
            ).first()

            if existing:
                # Update the existing correction's metadata if needed
                existing.similarity_score = correction_data.get('similarity_score', existing.similarity_score)
                existing.original_description = correction_data.get('original_description', existing.original_description)
                existing.original_format = correction_data.get('original_format', existing.original_format)
                existing.target_supplier_code = correction_data.get('target_supplier_code', existing.target_supplier_code)
                result = existing
            else:
                # Create new correction
                correction = UserCorrection(**correction_data)
                session.add(correction)
                result = correction

            # Only commit if we created the session (caller manages transaction if session provided)
            if not session_provided:
                session.commit()

            return result
        except Exception as e:
            # Only rollback if we created the session
            if not session_provided:
                session.rollback()
            raise
        finally:
            # Only close if we created the session
            if not session_provided:
                session.close()

    def get_user_corrections(self, supplier_code: str, supplier: str) -> List[UserCorrection]:
        """Get user corrections for a supplier code"""
        session = self.get_session()
        try:
            supplier_obj = session.query(Supplier).filter_by(code=supplier).first()
            if not supplier_obj:
                return []

            results = session.query(UserCorrection).filter(
                and_(
                    UserCorrection.original_supplier_id == supplier_obj.id,
                    UserCorrection.original_supplier_code == supplier_code,
                    UserCorrection.user_confirmed == True
                )
            ).all()

            return results
        finally:
            # Explicitly detach objects before closing session
            # This allows returned UserCorrection objects to be used after session closes
            session.expunge_all()
            session.close()

    def cache_match(self, search_text: str, product_id: int, similarity_score: float, method: str):
        """Cache a matching result"""
        session = self.get_session()
        try:
            # Create hash of search text
            search_hash = hashlib.md5(search_text.lower().encode()).hexdigest()

            # Check if exists
            existing = session.query(MatchingCache).filter_by(search_hash=search_hash).first()

            if existing:
                existing.hit_count += 1
                existing.last_used = datetime.utcnow()
            else:
                cache = MatchingCache(
                    search_text=search_text,
                    search_hash=search_hash,
                    matched_product_id=product_id,
                    similarity_score=similarity_score,
                    match_method=method
                )
                session.add(cache)

            session.commit()
        except Exception as e:
            session.rollback()
            print(f"Cache error: {e}")
        finally:
            session.close()

    def get_cached_match(self, search_text: str) -> Optional[Tuple[Product, float]]:
        """Get cached match if exists"""
        session = self.get_session()
        try:
            search_hash = hashlib.md5(search_text.lower().encode()).hexdigest()
            cache = session.query(MatchingCache).filter_by(search_hash=search_hash).first()

            if cache:
                product = session.query(Product).filter_by(id=cache.matched_product_id).first()
                # Validate product still exists (cache could be stale if product was deleted)
                if product:
                    result = (product, cache.similarity_score)
                else:
                    result = None  # Treat as cache miss if product no longer exists
            else:
                result = None
            return result
        finally:
            # Explicitly detach objects before closing session
            session.expunge_all()
            session.close()


if __name__ == "__main__":
    # Test database operations
    db_ops = DatabaseOperations()

    # Load master GTIN
    stats = db_ops.load_master_gtin("master_GTIN.xlsx")
    print(f"\n✓ Loaded {stats}")
