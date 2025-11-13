#!/usr/bin/env python3
"""
Import Excel file into database

Supports two formats:
1. Master GTIN format (original format with columns: GTIN, Produit, Marque, Format, etc.)
2. Simple format (any Excel with: GTIN, Product Name, and supplier code columns)

Usage:
    invoice-comparison-import input.xlsx
    invoice-comparison-import input.xlsx output.db  # Create new database
"""

import sys
import os
import pandas as pd
from datetime import datetime

from invoice_comparison.database.operations import DatabaseOperations
from invoice_comparison.database.schema import Product, Supplier, SupplierCode, get_session, Base
from invoice_comparison.utils import normalize_gtin


# Removed duplicate normalize_gtin function - now using centralized version from utils


def detect_format(df):
    """Detect which Excel format this is"""

    columns = [col.lower() for col in df.columns]

    # Master GTIN format
    if 'gtin' in columns and any('code colabor' in col.lower() for col in df.columns):
        return 'master_gtin'

    # Simple format
    if 'gtin' in columns:
        return 'simple'

    return 'unknown'


def import_master_gtin_format(excel_path, db_path):
    """Import master GTIN format (the original format)"""

    print(f"📋 Detected: Master GTIN format")
    print(f"   Loading from: {excel_path}")

    db_ops = DatabaseOperations(db_path=db_path)
    result = db_ops.load_master_gtin(excel_path)

    print(f"\n✅ Import complete!")
    print(f"   Products added: {result['products_added']}")
    print(f"   Products updated: {result['products_updated']}")
    print(f"   Mappings added: {result['mappings_added']}")
    print(f"   Mappings updated: {result['mappings_updated']}")


def import_simple_format(excel_path, db_path):
    """
    Import simple format Excel

    Expected columns:
    - GTIN (required)
    - Product Name or Produit (required)
    - Brand or Marque (optional)
    - Format (optional)
    - Packaging or Empaquetage (optional)
    - Category or Catégorie (optional)
    - Supplier code columns (e.g., "Colabor Code", "Mayrand Code", etc.)
    """

    print(f"📋 Detected: Simple format")
    print(f"   Loading from: {excel_path}")

    df = pd.read_excel(excel_path)

    print(f"   Found {len(df)} rows")
    print(f"   Columns: {', '.join(df.columns)}")

    # Map common column names
    column_mapping = {
        'gtin': ['gtin', 'GTIN', 'code barre', 'barcode'],
        'product_name': ['product name', 'produit', 'product', 'name', 'nom'],
        'brand': ['brand', 'marque'],
        'format': ['format', 'size', 'taille'],
        'packaging': ['packaging', 'empaquetage', 'emballage'],
        'category': ['category', 'catégorie', 'categorie']
    }

    # Find actual columns
    actual_columns = {}
    for key, possible_names in column_mapping.items():
        for col in df.columns:
            if col.lower() in [name.lower() for name in possible_names]:
                actual_columns[key] = col
                break

    if 'gtin' not in actual_columns:
        print("❌ Error: No GTIN column found!")
        print("   Required column: GTIN (or 'Code Barre', 'Barcode')")
        return

    if 'product_name' not in actual_columns:
        print("❌ Error: No Product Name column found!")
        print("   Required column: Product Name (or 'Produit', 'Name')")
        return

    print(f"\n📊 Mapped columns:")
    for key, col in actual_columns.items():
        print(f"   {key}: {col}")

    # Find supplier code columns
    supplier_columns = {}
    known_suppliers = {
        'colabor': ['colabor', 'code colabor'],
        'mayrand': ['mayrand', 'code mayrand'],
        'dube_loiselle': ['dube loiselle', 'dubé loiselle', 'dube', 'code dube'],
        'flb': ['flb', 'code flb'],
        'ben_deshaies': ['ben deshaies', 'deshaies', 'code ben']
    }

    for col in df.columns:
        col_lower = col.lower()
        for supplier_code, patterns in known_suppliers.items():
            if any(pattern in col_lower for pattern in patterns):
                supplier_columns[supplier_code] = col
                break

    if supplier_columns:
        print(f"\n🏢 Found supplier code columns:")
        for supplier, col in supplier_columns.items():
            print(f"   {supplier}: {col}")

    # Import data
    db_ops = DatabaseOperations(db_path=db_path)
    session = db_ops.get_session()

    stats = {
        'products_added': 0,
        'products_updated': 0,
        'codes_added': 0,
        'codes_skipped': 0,
        'rows_skipped': 0
    }

    # Pre-load all suppliers to avoid N+1 query problem
    # Query once instead of querying inside the loop for every row
    supplier_objects = {}
    if supplier_columns:
        for supplier_code in supplier_columns.keys():
            supplier_obj = session.query(Supplier).filter_by(code=supplier_code).first()
            if supplier_obj:
                supplier_objects[supplier_code] = supplier_obj
            else:
                print(f"   ⚠️  Warning: Supplier '{supplier_code}' not found in database")

    try:
        print(f"\n⚙️  Importing data...")

        for idx, row in df.iterrows():
            # Normalize GTIN (handles Excel floats and validates format)
            gtin = normalize_gtin(row[actual_columns['gtin']])

            # Skip invalid GTINs
            if not gtin:
                stats['rows_skipped'] += 1
                continue

            product_name = str(row.get(actual_columns['product_name'], '')).strip()
            if not product_name or product_name in ['nan', 'None']:
                product_name = f"Product {gtin}"

            # Get other fields
            brand = str(row.get(actual_columns.get('brand', ''), '')).strip() if 'brand' in actual_columns else None
            if brand in ['nan', 'None', '']:
                brand = None

            format_val = str(row.get(actual_columns.get('format', ''), '')).strip() if 'format' in actual_columns else None
            if format_val in ['nan', 'None', '']:
                format_val = None

            packaging = str(row.get(actual_columns.get('packaging', ''), '')).strip() if 'packaging' in actual_columns else None
            if packaging in ['nan', 'None', '']:
                packaging = None

            category = str(row.get(actual_columns.get('category', ''), '')).strip() if 'category' in actual_columns else None
            if category in ['nan', 'None', '']:
                category = None

            # Check if product exists
            product = session.query(Product).filter_by(gtin=gtin).first()

            if not product:
                # Create new product
                product = Product(
                    gtin=gtin,
                    product_name=product_name,
                    brand=brand,
                    format=format_val,
                    packaging=packaging,
                    category=category,
                    created_at=datetime.utcnow()
                )
                session.add(product)
                session.flush()
                stats['products_added'] += 1
            else:
                # Update with any new information
                updated = False
                if not product.product_name and product_name:
                    product.product_name = product_name
                    updated = True
                if not product.brand and brand:
                    product.brand = brand
                    updated = True
                if not product.format and format_val:
                    product.format = format_val
                    updated = True
                if not product.packaging and packaging:
                    product.packaging = packaging
                    updated = True
                if not product.category and category:
                    product.category = category
                    updated = True

                if updated:
                    product.updated_at = datetime.utcnow()
                    stats['products_updated'] += 1

            # Add supplier codes
            for supplier_code, col_name in supplier_columns.items():
                supplier_product_code = str(row.get(col_name, '')).strip()

                if supplier_product_code and supplier_product_code not in ['nan', 'None', '']:
                    # Get supplier from pre-loaded cache (avoids N+1 query problem)
                    supplier = supplier_objects.get(supplier_code)
                    if not supplier:
                        # Already warned during pre-load, skip silently
                        continue

                    # Check if code already exists
                    existing = session.query(SupplierCode).filter_by(
                        supplier_id=supplier.id,
                        supplier_code=supplier_product_code
                    ).first()

                    if existing:
                        # Update if it points to a different product
                        if existing.product_id != product.id:
                            existing.product_id = product.id
                            existing.active = True
                            existing.updated_at = datetime.utcnow()
                            stats['codes_added'] += 1  # Count as added since we updated
                        else:
                            stats['codes_skipped'] += 1
                    else:
                        # Create new supplier code
                        new_code = SupplierCode(
                            supplier_id=supplier.id,
                            product_id=product.id,
                            supplier_code=supplier_product_code,
                            active=True,
                            created_at=datetime.utcnow()
                        )
                        session.add(new_code)
                        stats['codes_added'] += 1

            # Commit every 100 rows
            if (idx + 1) % 100 == 0:
                session.commit()
                print(f"   Processed {idx + 1} rows...")

        session.commit()

        print(f"\n✅ Import complete!")
        print(f"   Products added: {stats['products_added']}")
        print(f"   Products updated: {stats['products_updated']}")
        print(f"   Supplier codes added: {stats['codes_added']}")
        print(f"   Supplier codes skipped (duplicates): {stats['codes_skipped']}")
        print(f"   Rows skipped (invalid): {stats['rows_skipped']}")

    except Exception as e:
        print(f"\n❌ Error during import: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def main():
    if len(sys.argv) < 2:
        print("Usage: invoice-comparison-import <input.xlsx> [output.db]")
        print("\nExamples:")
        print("  # Import into existing database")
        print("  invoice-comparison-import products.xlsx")
        print()
        print("  # Create new database from Excel")
        print("  invoice-comparison-import products.xlsx ~/.invoice-comparison/new_database.db")
        sys.exit(1)

    excel_path = sys.argv[1]

    if not os.path.exists(excel_path):
        print(f"❌ Error: File not found: {excel_path}")
        sys.exit(1)

    # Determine database path
    if len(sys.argv) >= 3:
        db_path = sys.argv[2]

        # Create new database if it doesn't exist
        if not os.path.exists(db_path):
            print(f"📝 Creating new database: {db_path}")

            # Create directory if needed
            db_dir = os.path.dirname(db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

            # Create database schema
            from sqlalchemy import create_engine
            db_engine = create_engine(f'sqlite:///{db_path}')
            Base.metadata.create_all(db_engine)

            # Add suppliers
            session = get_session(db_path)
            try:
                suppliers = [
                    Supplier(code='colabor', name='Colabor'),
                    Supplier(code='mayrand', name='Mayrand'),
                    Supplier(code='dube_loiselle', name='Dubé Loiselle'),
                    Supplier(code='flb', name='FLB'),
                    Supplier(code='ben_deshaies', name='Ben Deshaies'),
                    Supplier(code='gfs', name='GFS')
                ]
                for supplier in suppliers:
                    session.add(supplier)
                session.commit()
                print(f"   ✅ Initialized with 6 suppliers")
            finally:
                session.close()
    else:
        # Use default database path
        db_path = os.path.expanduser('~/.invoice-comparison/supplier_mappings.db')

    if not os.path.exists(db_path):
        print(f"❌ Error: Database not found: {db_path}")
        print(f"   Create it first or specify output path")
        sys.exit(1)

    print("=" * 80)
    print("EXCEL TO DATABASE IMPORT")
    print("=" * 80)
    print(f"Input: {excel_path}")
    print(f"Database: {db_path}")
    print("=" * 80 + "\n")

    # Detect format
    try:
        df = pd.read_excel(excel_path)
    except Exception as e:
        print(f"❌ Error: Failed to read Excel file: {excel_path}")
        print(f"   {type(e).__name__}: {e}")
        print("\nPlease ensure:")
        print("  - The file is a valid Excel file (.xlsx)")
        print("  - The file is not corrupted")
        print("  - The file is not open in another program")
        sys.exit(1)

    format_type = detect_format(df)

    if format_type == 'master_gtin':
        import_master_gtin_format(excel_path, db_path)
    elif format_type == 'simple':
        import_simple_format(excel_path, db_path)
    else:
        print("❌ Error: Could not detect Excel format")
        print("\nExpected columns:")
        print("  - GTIN (required)")
        print("  - Product Name or Produit (required)")
        print("  - Supplier code columns (optional, e.g., 'Colabor Code', 'Mayrand Code')")
        sys.exit(1)

    print("\n" + "=" * 80)
    print(f"✅ Database updated: {db_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()
