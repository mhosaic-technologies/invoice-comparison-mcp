"""
Database schema for the price comparison system
"""

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    Index,
    Boolean,
    Text,
    UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
import os

Base = declarative_base()


class Product(Base):
    """Master product table with GTIN codes"""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gtin = Column(String(14), unique=True, nullable=False, index=True)
    product_name = Column(String(500), nullable=False)
    brand = Column(String(200))
    format = Column(String(100))  # e.g., "3 KG", "12X454 G"
    packaging = Column(String(100))  # e.g., "BOX", "CASE"
    category = Column(String(100))
    aliments_quebec = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    supplier_codes = relationship("SupplierCode", back_populates="product")

    __table_args__ = (
        Index('idx_product_search', 'product_name', 'brand'),
    )

    def __repr__(self):
        return f"<Product(gtin='{self.gtin}', name='{self.product_name[:30]}')>"


class Supplier(Base):
    """Supplier master table"""
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    code = Column(String(50), unique=True, nullable=False)  # e.g., "colabor", "dube_loiselle"
    full_name = Column(String(200))
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    supplier_codes = relationship("SupplierCode", back_populates="supplier")

    def __repr__(self):
        return f"<Supplier(code='{self.code}', name='{self.name}')>"


class SupplierCode(Base):
    """Mapping between supplier-specific codes and GTIN"""
    __tablename__ = "supplier_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=False)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    supplier_code = Column(String(50), nullable=False)  # Supplier-specific product code
    price = Column(Float)  # Current price (can be updated)
    price_updated_at = Column(DateTime)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    supplier = relationship("Supplier", back_populates="supplier_codes")
    product = relationship("Product", back_populates="supplier_codes")

    __table_args__ = (
        Index('idx_supplier_code_lookup', 'supplier_id', 'supplier_code'),
        Index('idx_product_supplier', 'product_id', 'supplier_id'),
        UniqueConstraint('supplier_id', 'supplier_code', name='uq_supplier_product_code'),
    )

    def __repr__(self):
        # Safely access supplier.code, handling detached instances
        try:
            supplier_code = self.supplier.code if self.supplier else 'unknown'
        except:
            supplier_code = 'detached'
        return f"<SupplierCode(supplier={supplier_code}, code='{self.supplier_code}')>"


class UserCorrection(Base):
    """Store user corrections for learning"""
    __tablename__ = "user_corrections"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Original product from invoice
    original_supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=False)
    original_supplier_code = Column(String(50), nullable=False)
    original_description = Column(Text, nullable=False)
    original_format = Column(String(100))

    # Corrected mapping
    matched_product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    target_supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=False)
    target_supplier_code = Column(String(50), nullable=False)

    # Metadata
    similarity_score = Column(Float)  # Original match score
    user_confirmed = Column(Boolean, default=True)
    notes = Column(Text)
    created_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    original_supplier = relationship("Supplier", foreign_keys=[original_supplier_id])
    target_supplier = relationship("Supplier", foreign_keys=[target_supplier_id])
    matched_product = relationship("Product", foreign_keys=[matched_product_id])

    __table_args__ = (
        Index('idx_correction_lookup', 'original_supplier_id', 'original_supplier_code'),
    )

    def __repr__(self):
        return f"<UserCorrection(original='{self.original_description[:30]}')>"


class ComparisonHistory(Base):
    """Store comparison history for auditing"""
    __tablename__ = "comparison_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_number = Column(String(50))
    invoice_date = Column(DateTime)
    source_supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=False)
    target_supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=False)

    total_products = Column(Integer)
    matched_products = Column(Integer)
    total_original_cost = Column(Float)
    total_comparison_cost = Column(Float)
    potential_savings = Column(Float)

    comparison_file_path = Column(String(500))  # Path to detailed results
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    source_supplier = relationship("Supplier", foreign_keys=[source_supplier_id])
    target_supplier = relationship("Supplier", foreign_keys=[target_supplier_id])

    def __repr__(self):
        return f"<ComparisonHistory(invoice='{self.invoice_number}', savings={self.potential_savings})>"


class MatchingCache(Base):
    """Cache fuzzy matching results for performance"""
    __tablename__ = "matching_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    search_text = Column(String(500), nullable=False, index=True)
    search_hash = Column(String(64), unique=True, nullable=False, index=True)  # MD5 hash
    matched_product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    similarity_score = Column(Float, nullable=False)
    match_method = Column(String(50))  # 'gtin', 'fuzzy_name', 'user_correction'
    created_at = Column(DateTime, default=datetime.utcnow)
    hit_count = Column(Integer, default=1)
    last_used = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    matched_product = relationship("Product", foreign_keys=[matched_product_id])

    def __repr__(self):
        return f"<MatchingCache(search='{self.search_text[:30]}', score={self.similarity_score})>"


# Database initialization
def init_database(db_path="data/supplier_mappings.db"):
    """
    Initialize the database and create all tables

    Args:
        db_path: Path to SQLite database file
    """
    # Create data directory if it doesn't exist
    db_dir = os.path.dirname(db_path)
    if db_dir:  # Only create if path contains a directory
        os.makedirs(db_dir, exist_ok=True)

    # Create engine
    engine = create_engine(f'sqlite:///{db_path}', echo=False)

    # Create all tables
    Base.metadata.create_all(engine)

    print(f"Database initialized at: {db_path}")

    # Create session maker
    Session = sessionmaker(bind=engine)

    return engine, Session


def get_session(db_path="data/supplier_mappings.db"):
    """Get a database session"""
    engine = create_engine(f'sqlite:///{db_path}', echo=False)
    Session = sessionmaker(bind=engine)
    return Session()


if __name__ == "__main__":
    # Initialize database when run directly
    engine, Session = init_database()
    print("✓ Database schema created successfully!")

    # Create a test session
    session = Session()

    # Add default suppliers
    suppliers = [
        {"code": "colabor", "name": "Colabor", "full_name": "Colabor Inc."},
        {"code": "dube_loiselle", "name": "Dubé Loiselle", "full_name": "Dubé Loiselle Inc."},
        {"code": "mayrand", "name": "Mayrand", "full_name": "Mayrand Plus"},
        {"code": "ben_deshaies", "name": "Ben Deshaies", "full_name": "Ben Deshaies & Fils"},
        {"code": "flb", "name": "FLB", "full_name": "FLB Distribution"},
        {"code": "sanifa", "name": "Sanifa", "full_name": "Sanifa Inc."},
    ]

    for s in suppliers:
        existing = session.query(Supplier).filter_by(code=s["code"]).first()
        if not existing:
            supplier = Supplier(**s)
            session.add(supplier)
            print(f"  Added supplier: {s['name']}")

    session.commit()
    print("✓ Default suppliers added!")
    session.close()
