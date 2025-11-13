"""
MCP Server for Invoice Comparison System
"""

import json
import os
from typing import Any, Dict, List
import base64
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, EmbeddedResource

from invoice_comparison.comparison_engine import ComparisonEngine
from invoice_comparison.database.operations import DatabaseOperations


# Initialize server
app = Server("invoice-comparison")

# Database path in user's home directory
DB_DIR = os.path.expanduser('~/.invoice-comparison')
DB_PATH = os.path.join(DB_DIR, 'supplier_mappings.db')

# Initialize database if it doesn't exist
def init_database():
    """Initialize database if it doesn't exist"""
    if not os.path.exists(DB_PATH):
        print(f"Initializing database at {DB_PATH}...", flush=True)
        os.makedirs(DB_DIR, exist_ok=True)

        # Try to copy demo database from package
        try:
            # Try modern importlib.resources first (Python 3.9+)
            try:
                from importlib.resources import files
                demo_db_path = files('invoice_comparison').joinpath('data/demo_database.db')
                if demo_db_path.is_file():
                    import shutil
                    shutil.copy2(demo_db_path, DB_PATH)
                    print(f"Demo database initialized with 100 sample products.", flush=True)
                    return
            except Exception as e:
                # Fallback to pkg_resources
                print(f"Could not load demo database using importlib.resources: {e}", flush=True)
                import pkg_resources
                demo_db = pkg_resources.resource_filename('invoice_comparison', 'data/demo_database.db')
                if os.path.exists(demo_db):
                    import shutil
                    shutil.copy2(demo_db, DB_PATH)
                    print(f"Demo database initialized with 100 sample products.", flush=True)
                    return
        except Exception as e:
            print(f"Could not load demo database: {e}. Creating empty database.", flush=True)

        # Create empty database if demo not available
        from invoice_comparison.database.schema import Base, Supplier, get_session
        from sqlalchemy import create_engine

        engine_db = create_engine(f'sqlite:///{DB_PATH}')
        Base.metadata.create_all(engine_db)

        # Add suppliers
        session = get_session(DB_PATH)
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
            print(f"Empty database initialized. Please import product data.", flush=True)
        finally:
            session.close()

# Initialize database
init_database()

# Initialize engine with database path
engine = ComparisonEngine(db_path=DB_PATH)
db_ops = DatabaseOperations(db_path=DB_PATH)


@app.list_tools()
async def list_tools() -> List[Tool]:
    """List available tools"""
    return [
        Tool(
            name="compare_invoice",
            description="Compare invoice products against a target supplier. When extracting from a PDF invoice, extract all pages to capture all products. Returns matches with similarity scores and potential savings.",
            inputSchema={
                "type": "object",
                "properties": {
                    "csv_content": {
                        "type": "string",
                        "description": "CSV content with all products from the invoice. If the invoice PDF has multiple pages, extract from all pages. Required columns: supplier_code,product_name,brand,format,packaging,category,price,quantity"
                    },
                    "source_supplier": {
                        "type": "string",
                        "description": "Source supplier code (e.g., 'dube_loiselle', 'mayrand', 'ben_deshaies')",
                        "enum": ["dube_loiselle", "colabor", "mayrand", "ben_deshaies", "flb", "sanifa"]
                    },
                    "target_supplier": {
                        "type": "string",
                        "description": "Target supplier code to compare against (e.g., 'colabor')",
                        "enum": ["dube_loiselle", "colabor", "mayrand", "ben_deshaies", "flb", "sanifa"]
                    },
                    "min_similarity": {
                        "type": "number",
                        "description": "Minimum similarity threshold (0-100). Default: 60.0",
                        "default": 60.0
                    }
                },
                "required": ["csv_content", "source_supplier", "target_supplier"]
            }
        ),
        Tool(
            name="find_product",
            description="Search for a product at target supplier using fuzzy matching. Use this when user asks 'find X product' or 'search for X'. Returns ranked matches. DO NOT use this when importing corrections from Excel - use import_corrections instead.",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_name": {
                        "type": "string",
                        "description": "Product name/description"
                    },
                    "supplier_code": {
                        "type": "string",
                        "description": "Product code at source supplier (optional)"
                    },
                    "brand": {
                        "type": "string",
                        "description": "Brand name (optional)"
                    },
                    "format": {
                        "type": "string",
                        "description": "Product format/size (optional)"
                    },
                    "source_supplier": {
                        "type": "string",
                        "description": "Source supplier code",
                        "enum": ["dube_loiselle", "colabor", "mayrand", "ben_deshaies", "flb", "sanifa"]
                    },
                    "target_supplier": {
                        "type": "string",
                        "description": "Target supplier code",
                        "enum": ["dube_loiselle", "colabor", "mayrand", "ben_deshaies", "flb", "sanifa"]
                    },
                    "min_similarity": {
                        "type": "number",
                        "description": "Minimum similarity threshold (0-100). Default: 60.0",
                        "default": 60.0
                    },
                    "max_results": {
                        "type": "number",
                        "description": "Maximum number of results to return. Default: 5",
                        "default": 5
                    }
                },
                "required": ["product_name", "source_supplier", "target_supplier"]
            }
        ),
        Tool(
            name="save_correction",
            description="Save a SINGLE user correction for one product. Use this ONLY when user verbally confirms a match (e.g., 'save that match' or 'code X matches Y'). Requires GTIN of existing product. For Excel imports with multiple corrections, use import_corrections instead.",
            inputSchema={
                "type": "object",
                "properties": {
                    "original_supplier_code": {
                        "type": "string",
                        "description": "Original product code at source supplier"
                    },
                    "source_supplier": {
                        "type": "string",
                        "description": "Source supplier code",
                        "enum": ["dube_loiselle", "colabor", "mayrand", "ben_deshaies", "flb", "sanifa"]
                    },
                    "matched_product_gtin": {
                        "type": "string",
                        "description": "GTIN of the correct matched product"
                    },
                    "similarity_score": {
                        "type": "number",
                        "description": "Similarity score of the match (0-100)"
                    },
                    "user_confirmed": {
                        "type": "boolean",
                        "description": "Whether user confirmed this match as correct",
                        "default": True
                    }
                },
                "required": ["original_supplier_code", "source_supplier", "matched_product_gtin"]
            }
        ),
        Tool(
            name="list_suppliers",
            description="Get list of available suppliers in the database",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_product_by_code",
            description="Look up existing product details by exact supplier code. Use ONLY when user asks 'what is code X' or 'show me product code X'. DO NOT use to validate codes from Excel files. DO NOT use before calling import_corrections.",
            inputSchema={
                "type": "object",
                "properties": {
                    "supplier_code": {
                        "type": "string",
                        "description": "Product code at supplier"
                    },
                    "supplier": {
                        "type": "string",
                        "description": "Supplier code",
                        "enum": ["dube_loiselle", "colabor", "mayrand", "ben_deshaies", "flb", "sanifa"]
                    }
                },
                "required": ["supplier_code", "supplier"]
            }
        ),
        Tool(
            name="import_corrections",
            description="Import corrections from Excel file uploaded by user. ALWAYS call this immediately when user uploads an Excel file with corrections. Creates new product mappings even if codes don't exist. DO NOT validate codes first. DO NOT call get_product_by_code. DO NOT call find_product. Just extract CSV from Excel and call this tool directly. Extract all rows from the Excel file. To UPDATE PRICES: Include prices in any reasonably named column - we accept 'Price', 'Target Price', 'New Target Price', or '{Supplier} Price' (case-insensitive).",
            inputSchema={
                "type": "object",
                "properties": {
                    "csv_content": {
                        "type": "string",
                        "description": "CSV content with all rows. Required columns: 'GTIN', 'Source Code', 'Target Code'. For price updates: include a price column with any reasonable name like 'Price', 'Target Price', 'New Target Price', 'Colabor Price', etc. (case-insensitive). The system will automatically find and use the price data."
                    },
                    "source_supplier": {
                        "type": "string",
                        "description": "Source supplier code (e.g., 'dube_loiselle', 'mayrand', 'ben_deshaies')",
                        "enum": ["dube_loiselle", "colabor", "mayrand", "ben_deshaies", "flb", "sanifa"]
                    },
                    "target_supplier": {
                        "type": "string",
                        "description": "Target supplier code (e.g., 'colabor')",
                        "enum": ["dube_loiselle", "colabor", "mayrand", "ben_deshaies", "flb", "sanifa"]
                    }
                },
                "required": ["csv_content", "source_supplier", "target_supplier"]
            }
        ),
        Tool(
            name="list_comparison_files",
            description="List all Excel comparison files in the output directory with their details",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="read_comparison_file",
            description="Read and parse an Excel comparison file to view detailed product matches and analysis",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Name of the Excel file to read (use list_comparison_files to see available files)"
                    }
                },
                "required": ["filename"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> List[TextContent]:
    """Handle tool calls"""

    try:
        if name == "compare_invoice":
            # Compare full invoice
            csv_content = arguments["csv_content"]
            source_supplier = arguments["source_supplier"]
            target_supplier = arguments["target_supplier"]
            min_similarity = arguments.get("min_similarity", 60.0)

            # Validate min_similarity range
            if not (0 <= min_similarity <= 100):
                return [TextContent(
                    type="text",
                    text=f"❌ Invalid min_similarity: {min_similarity}\n\nMust be between 0 and 100."
                )]

            report = engine.compare_invoice(
                csv_content=csv_content,
                source_supplier=source_supplier,
                target_supplier=target_supplier,
                min_similarity=min_similarity
            )

            result = report.to_dict()

            # Generate Excel file and save to disk
            excel_bytes = report.to_excel_bytes()

            # Save to Downloads folder for easy user access
            output_dir = os.path.expanduser('~/Downloads')
            os.makedirs(output_dir, exist_ok=True)

            from datetime import datetime
            import random
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            # Add random suffix to prevent race condition if multiple comparisons run in same second
            random_suffix = random.randint(1000, 9999)
            filename = f"invoice_comparison_{report.source_supplier}_to_{report.target_supplier}_{timestamp}_{random_suffix}.xlsx"
            filepath = os.path.join(output_dir, filename)

            with open(filepath, 'wb') as f:
                f.write(excel_bytes)

            # Also encode as base64 for potential embedding
            excel_base64 = base64.b64encode(excel_bytes).decode('utf-8')

            # Format response for Claude
            response = format_comparison_report(result)

            # Add Excel file information to response
            response += f"\n\n📊 **Excel Report Generated**\n"
            response += f"✅ File successfully saved at:\n"
            response += f"   `{filepath}`\n\n"
            response += f"📖 **To view the detailed Excel contents**, use:\n"
            response += f"   `read_comparison_file` with filename: `{filename}`\n\n"
            response += f"Or use `list_comparison_files` to see all available comparison files.\n\n"
            response += f"**Excel Contents:**\n"
            response += f"- All {report.total_items} products from the invoice\n"
            response += f"- GTIN codes in the first column\n"
            response += f"- Color-coded rows (green=exact match, yellow=fuzzy match, red=no match)\n"
            response += f"- Complete product details, prices, and match information\n"

            return [
                TextContent(
                    type="text",
                    text=response
                ),
                EmbeddedResource(
                    type="resource",
                    resource={
                        "uri": f"data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{excel_base64}",
                        "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "text": filename
                    }
                )
            ]

        elif name == "find_product":
            # Find single product
            product_info = {
                'product_name': arguments["product_name"],
                'supplier_code': arguments.get("supplier_code", ""),
                'brand': arguments.get("brand", ""),
                'format': arguments.get("format", ""),
                'packaging': ""
            }

            source_supplier = arguments["source_supplier"]
            target_supplier = arguments["target_supplier"]
            min_similarity = arguments.get("min_similarity", 60.0)
            max_results = arguments.get("max_results", 5)

            # Validate min_similarity range
            if not (0 <= min_similarity <= 100):
                return [TextContent(
                    type="text",
                    text=f"❌ Invalid min_similarity: {min_similarity}\n\nMust be between 0 and 100."
                )]

            # Validate max_results
            if not (1 <= max_results <= 100):
                return [TextContent(
                    type="text",
                    text=f"❌ Invalid max_results: {max_results}\n\nMust be between 1 and 100."
                )]

            matches = engine.matcher.find_matches(
                product_info=product_info,
                source_supplier=source_supplier,
                target_supplier=target_supplier,
                min_similarity=min_similarity,
                max_results=max_results
            )

            response = format_product_matches(product_info, matches, target_supplier)

            return [TextContent(
                type="text",
                text=response
            )]

        elif name == "save_correction":
            # Save user correction
            original_code = arguments["original_supplier_code"]
            source_supplier = arguments["source_supplier"]
            matched_gtin = arguments["matched_product_gtin"]
            similarity = arguments.get("similarity_score", 100.0)
            confirmed = arguments.get("user_confirmed", True)

            # Find the matched product
            matched_product = db_ops.find_product_by_gtin(matched_gtin)

            if not matched_product:
                return [TextContent(
                    type="text",
                    text=f"❌ Error: Product with GTIN {matched_gtin} not found in database"
                )]

            # Save correction
            correction_data = {
                'original_supplier_code': original_code,
                'source_supplier': source_supplier,
                'matched_product_id': matched_product.id,
                'similarity_score': similarity,
                'user_confirmed': confirmed
            }

            correction = db_ops.add_user_correction(correction_data)

            response = f"""✅ Correction saved successfully!

Original Code: {original_code} ({source_supplier})
Matched Product: {matched_product.product_name}
GTIN: {matched_product.gtin}
Similarity: {similarity:.1f}%

This correction will be used to improve future matches."""

            return [TextContent(
                type="text",
                text=response
            )]

        elif name == "list_suppliers":
            # Get all suppliers
            session = db_ops.get_session()
            try:
                from invoice_comparison.database.schema import Supplier
                suppliers = session.query(Supplier).all()

                response = "📦 Available Suppliers:\n\n"
                for supplier in suppliers:
                    response += f"- **{supplier.code}**: {supplier.name}\n"

                return [TextContent(
                    type="text",
                    text=response
                )]
            finally:
                session.close()

        elif name == "get_product_by_code":
            # Get product details
            supplier_code = arguments["supplier_code"]
            supplier = arguments["supplier"]

            result = db_ops.find_product_by_supplier_code(supplier_code, supplier)

            if not result:
                return [TextContent(
                    type="text",
                    text=f"❌ Product not found: {supplier_code} at {supplier}"
                )]

            product, supplier_code_obj = result

            price_str = f"${supplier_code_obj.price:.2f}" if supplier_code_obj.price else "N/A"
            active_str = "Yes" if supplier_code_obj.active else "No"

            response = f"""📦 Product Details

**Product**: {product.product_name}
**Brand**: {product.brand or 'N/A'}
**Format**: {product.format or 'N/A'}
**Packaging**: {product.packaging or 'N/A'}
**Category**: {product.category or 'N/A'}
**GTIN**: {product.gtin}

**At {supplier}**:
- Code: {supplier_code_obj.supplier_code}
- Price: {price_str}
- Active: {active_str}"""

            return [TextContent(
                type="text",
                text=response
            )]

        elif name == "import_corrections":
            # Import corrections from edited Excel
            csv_content = arguments["csv_content"]
            source_supplier = arguments["source_supplier"]
            target_supplier = arguments["target_supplier"]

            # Call the import_corrections method
            result = engine.import_corrections(
                csv_content=csv_content,
                source_supplier=source_supplier,
                target_supplier=target_supplier
            )

            # Format response
            summary = result['summary']
            response = f"""## 📝 Import Summary

**New Products Created**: {summary['total_products_created']}
**Products Updated**: {summary['total_products_updated']}
**Mappings/Corrections Saved**: {summary['total_saved']}
**Failed**: {summary['total_failed']}
**Skipped**: {summary['total_skipped']}

"""

            if result['products_created']:
                response += "### ✨ New Products Created:\n\n"
                for product in result['products_created']:
                    response += f"**{product['source_code']}**: {product['product_name']}\n"
                    response += f"  → GTIN: {product['gtin']}\n\n"

            if result['products_updated']:
                response += "### 🔄 Products Updated:\n\n"
                for product in result['products_updated']:
                    response += f"**{product['product_name']}** (GTIN: {product['gtin']})\n"
                    response += f"  → Updated fields: {', '.join(product['updated_fields'])}\n\n"

            if result['saved']:
                response += "### ✅ Mappings/Corrections Saved:\n\n"
                for correction in result['saved']:
                    response += f"**{correction['source_code']}**: {correction['source_product']}\n"
                    response += f"  → Matched to: **{correction['target_code']}** - {correction['target_product']}\n"
                    response += f"  → GTIN: {correction['gtin']}\n"
                    if correction.get('product_created'):
                        response += f"  → 🆕 Product was created\n"
                    if correction.get('product_updated'):
                        response += f"  → 🔄 Product was updated\n"
                    if correction.get('note'):
                        response += f"  → ℹ️ {correction['note']}\n"
                    response += "\n"

            if result['failed']:
                response += "\n### ❌ Failed:\n\n"
                for failure in result['failed']:
                    response += f"**{failure.get('source_code', 'N/A')}**: {failure.get('product_name', 'Unknown')}\n"
                    response += f"  → Reason: {failure['reason']}\n\n"

            if result['skipped']:
                response += "\n### ⚠️ Skipped:\n\n"
                for skip in result['skipped']:
                    response += f"- {skip['source_code']}: {skip['reason']}\n"

            if summary['total_saved'] > 0 or summary['total_products_created'] > 0:
                response += "\n---\n\n"
                response += "✅ **Knowledge base updated successfully!**\n\n"
                if summary['total_products_created'] > 0:
                    response += f"- Added {summary['total_products_created']} new product(s) to the master database\n"
                if summary['total_products_updated'] > 0:
                    response += f"- Updated {summary['total_products_updated']} existing product(s) with new information\n"
                if summary['total_saved'] > 0:
                    response += f"- Created {summary['total_saved']} supplier code mapping(s)\n"
                response += "\nThese will be automatically used in future comparisons."

            return [TextContent(
                type="text",
                text=response
            )]

        elif name == "list_comparison_files":
            # List all Excel files in Downloads folder
            output_dir = os.path.expanduser('~/Downloads')

            if not os.path.exists(output_dir):
                return [TextContent(
                    type="text",
                    text="No comparison files found. The output directory doesn't exist yet.\n\nRun a comparison first to generate Excel files."
                )]

            files = []
            for filename in os.listdir(output_dir):
                if filename.endswith('.xlsx') and filename.startswith('invoice_comparison_'):
                    filepath = os.path.join(output_dir, filename)
                    stat = os.stat(filepath)
                    files.append({
                        'name': filename,
                        'size': stat.st_size,
                        'modified': stat.st_mtime
                    })

            if not files:
                return [TextContent(
                    type="text",
                    text="No comparison files found in the output directory.\n\nRun a comparison to generate Excel files."
                )]

            # Sort by modification time (newest first)
            files.sort(key=lambda x: x['modified'], reverse=True)

            from datetime import datetime
            response = "## 📁 Available Comparison Files\n\n"
            response += f"**Location**: `{output_dir}`\n\n"

            for file in files:
                size_kb = file['size'] / 1024
                mod_time = datetime.fromtimestamp(file['modified']).strftime('%Y-%m-%d %H:%M:%S')
                response += f"### {file['name']}\n"
                response += f"- **Size**: {size_kb:.1f} KB\n"
                response += f"- **Modified**: {mod_time}\n\n"

            response += f"\n**Total Files**: {len(files)}\n\n"
            response += "Use `read_comparison_file` with the filename to view the detailed contents."

            return [TextContent(
                type="text",
                text=response
            )]

        elif name == "read_comparison_file":
            # Read and parse Excel comparison file
            filename = arguments["filename"]

            # Security: Prevent path traversal attacks by using only basename
            # This strips any directory components like "../" from the filename
            safe_filename = os.path.basename(filename)

            # Additional validation: ensure filename is safe
            if not safe_filename or safe_filename.startswith('.') or not safe_filename.endswith('.xlsx'):
                return [TextContent(
                    type="text",
                    text=f"❌ Invalid filename: {filename}\n\nFilename must end with .xlsx and cannot contain path separators."
                )]

            output_dir = os.path.expanduser('~/Downloads')
            filepath = os.path.join(output_dir, safe_filename)

            if not os.path.exists(filepath):
                return [TextContent(
                    type="text",
                    text=f"❌ File not found: {safe_filename}\n\nUse `list_comparison_files` to see available files."
                )]

            try:
                import pandas as pd

                # Read the Excel file
                df = pd.read_excel(filepath)

                # Validate this is a comparison file (must have Match Type column)
                if 'Match Type' not in df.columns:
                    return [TextContent(
                        type="text",
                        text=f"❌ Invalid comparison file: {safe_filename}\n\nThis file does not appear to be a comparison output. Missing 'Match Type' column.\n\nUse `list_comparison_files` to see valid comparison files."
                    )]

                # Extract summary info
                total_products = len(df)
                exact_matches = len(df[df['Match Type'] == 'Exact Match'])
                fuzzy_matches = len(df[df['Match Type'] == 'Fuzzy Match'])
                low_confidence_matches = len(df[df['Match Type'] == 'Low Confidence'])
                no_matches = len(df[df['Match Type'] == 'No Match'])

                response = f"## 📊 Comparison File: {safe_filename}\n\n"
                response += f"**Total Products**: {total_products}\n\n"

                if total_products == 0:
                    response += "⚠️ **No products found in this file.**\n\n"
                else:
                    response += f"### Match Summary\n\n"
                    response += f"- ✅ **Exact Matches**: {exact_matches} ({exact_matches/total_products*100:.1f}%)\n"
                    response += f"- 🔍 **Fuzzy Matches**: {fuzzy_matches} ({fuzzy_matches/total_products*100:.1f}%)\n"
                    response += f"- ⚠️ **Low Confidence**: {low_confidence_matches} ({low_confidence_matches/total_products*100:.1f}%)\n"
                    response += f"- ❌ **No Matches**: {no_matches} ({no_matches/total_products*100:.1f}%)\n\n"

                    # Show first few rows as example
                    response += "### Sample Data (first 5 products)\n\n"
                    for idx, row in df.head(5).iterrows():
                        response += f"**{idx+1}. {row.get('Product Name', 'N/A')}**\n"
                        response += f"- Source Code: {row.get('Source Code', 'N/A')}\n"
                        response += f"- Match Type: {row.get('Match Type', 'N/A')}\n"
                        if pd.notna(row.get('Target Code')):
                            response += f"- Target Code: {row.get('Target Code', 'N/A')}\n"
                            response += f"- Target Name: {row.get('Target Product Name', 'N/A')}\n"
                            if pd.notna(row.get('Similarity')):
                                response += f"- Similarity: {row.get('Similarity', 0):.1f}%\n"
                        response += "\n"

                response += f"\n**Full file location**: `{filepath}`\n\n"
                response += "The complete Excel file contains all products with GTIN codes, prices, and detailed match information."

                return [TextContent(
                    type="text",
                    text=response
                )]

            except Exception as e:
                return [TextContent(
                    type="text",
                    text=f"❌ Error reading file: {str(e)}"
                )]

        else:
            return [TextContent(
                type="text",
                text=f"Unknown tool: {name}"
            )]

    except Exception as e:
        return [TextContent(
            type="text",
            text=f"❌ Error: {str(e)}"
        )]


def format_comparison_report(report: Dict) -> str:
    """Format comparison report for Claude"""
    summary = report["summary"]
    financials = report["financials"]

    response = f"""# Invoice Comparison Report

## Summary
- **Source**: {report["source_supplier"]}
- **Target**: {report["target_supplier"]}
- **Total Items**: {summary["total_items"]}
- **Match Rate**: {summary["match_rate"]}
  - Exact matches: {summary["exact_matches"]}
  - Fuzzy matches: {summary["fuzzy_matches"]}
  - Low confidence matches: {summary["low_confidence_matches"]}
  - No matches: {summary["no_matches"]}

## Financial Summary
- **Original Total**: ${financials["original_total"]:.2f}
- **Target Total**: ${financials["target_total"]:.2f}
- **Potential Savings**: ${financials["potential_savings"]:.2f} ({financials["savings_percent"]:.1f}%)

## Detailed Results

"""

    for i, item in enumerate(report["items"], 1):
        orig = item["original"]
        match = item["match"]

        response += f"\n### {i}. {orig['name']}\n"
        response += f"- **Original**: {orig['code']} | {orig['brand']} | {orig['format']}\n"
        response += f"- **Price**: ${orig['price']:.2f} × {orig['quantity']:.0f} = ${orig['total']:.2f}\n"

        if match["product"]:
            prod = match["product"]
            response += f"- **Match**: {prod['name']} ({match['similarity']:.1f}% {match['match_type']})\n"
            response += f"  - Brand: {prod['brand']}\n"
            response += f"  - Format: {prod['format']}\n"
            response += f"  - GTIN: {prod['gtin']}\n"
            response += f"  - Code: {prod['code']}\n"

            if match["price_comparison"]:
                pc = match["price_comparison"]
                if pc["savings"] and pc["savings"] > 0:
                    response += f"  - 💰 **Savings**: +${pc['savings']:.2f} (+{pc['savings_percent']:.1f}%)\n"
                elif pc["savings"] and pc["savings"] < 0:
                    response += f"  - ⚠️ **More expensive**: ${abs(pc['savings']):.2f} ({abs(pc['savings_percent']):.1f}%)\n"

            if item.get("alternatives") and len(item["alternatives"]) > 0:
                response += f"  - **Alternatives**: {len(item['alternatives'])} other options available\n"
        else:
            response += f"- **Match**: ❌ Not found at {report['target_supplier']}\n"

    return response


def format_product_matches(product_info: Dict, matches: List, target_supplier: str) -> str:
    """Format product match results"""
    response = f"""# Product Search Results

**Searching for**: {product_info['product_name']}
**Brand**: {product_info.get('brand') or 'N/A'}
**Format**: {product_info.get('format') or 'N/A'}
**Target Supplier**: {target_supplier}

"""

    if not matches:
        response += "❌ No matches found\n"
        return response

    response += f"✅ Found {len(matches)} match(es):\n\n"

    for i, match in enumerate(matches, 1):
        response += f"## {i}. {match.product.product_name}\n"
        response += f"- **Similarity**: {match.similarity_score:.1f}% ({match.match_type})\n"
        response += f"- **Brand**: {match.product.brand or 'N/A'}\n"
        response += f"- **Format**: {match.product.format or 'N/A'}\n"
        response += f"- **GTIN**: {match.product.gtin}\n"
        response += f"- **Code**: {match.supplier_code or 'N/A'}\n"

        if match.price:
            response += f"- **Price**: ${match.price:.2f}\n"

        if match.match_type == 'fuzzy':
            response += f"- **Detailed Scores**:\n"
            response += f"  - Brand: {match.brand_score:.0f}%\n"
            response += f"  - Product: {match.product_type_score:.0f}%\n"
            response += f"  - Format: {match.format_score:.0f}%\n"
            response += f"  - Packaging: {match.packaging_score:.0f}%\n"

        response += "\n"

    return response


async def async_main():
    """Run the MCP server"""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


def main():
    """Entry point for the MCP server"""
    import asyncio
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
