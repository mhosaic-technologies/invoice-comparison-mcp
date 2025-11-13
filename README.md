# Invoice Comparison MCP Server

AI-powered invoice comparison system for Claude Desktop. Compare supplier invoices instantly to find equivalent products and make informed purchasing decisions.

## Features

- **Automatic Product Matching**: Uses GTIN codes and fuzzy matching to find equivalent products across suppliers
- **Excel Reports**: Generates detailed comparison reports with color-coded match quality
- **Database Growth**: Import corrections and new products to continuously improve matching
- **Multi-Supplier Support**: Built-in support for Colabor, Mayrand, Dubé Loiselle, FLB, Ben Deshaies, and GFS
- **Easy Management**: Command-line tools for importing Excel files and merging databases

## Quick Start

### Installation

#### Option 1: Using uvx (Recommended)

1. **Install uv** (if not already installed):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. **Configure Claude Desktop**:

Edit your Claude Desktop config file:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add this configuration:

**macOS:**
```json
{
  "mcpServers": {
    "invoice-comparison": {
      "command": "/Users/YOUR_USERNAME/.local/bin/uvx",
      "args": [
        "--from",
        "git+https://github.com/mhosaic-technologies/invoice-comparison-mcp",
        "invoice-comparison-server"
      ]
    }
  }
}
```
*Replace `YOUR_USERNAME` with your actual macOS username*

**Windows:**
```json
{
  "mcpServers": {
    "invoice-comparison": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/mhosaic-technologies/invoice-comparison-mcp",
        "invoice-comparison-server"
      ]
    }
  }
}
```

3. **Restart Claude Desktop**

That's it! The first time you use it, uvx will automatically:
- Download and install the package
- Set up a virtual environment
- Initialize the database with sample products

#### Option 2: Install from PyPI (When Published)

```bash
# Install from PyPI (when package is published)
pip install invoice-comparison-mcp
```

Then configure Claude Desktop with just `uvx invoice-comparison-mcp`.

### First Use

1. Open Claude Desktop
2. Test by asking: "What suppliers do you have?"
3. You should see: Colabor, Mayrand, Dubé Loiselle, FLB, Ben Deshaies, GFS

### Importing Full Database

The package comes with 100 sample products. To get the full database with 41,000+ products:

1. **Download the full database** (provided separately)
2. **Replace the demo database**:
```bash
cp full_supplier_mappings.db ~/.invoice-comparison/supplier_mappings.db
```

Or import from Excel:
```bash
uvx --from invoice-comparison-mcp invoice-comparison-import your_products.xlsx
```

## Usage

### Compare Invoices

1. Drag and drop an invoice PDF into Claude Desktop
2. Say: **"Compare this to Colabor"**
3. Get an Excel file in your **Downloads folder** with:
   - All products from your invoice
   - Matched products from Colabor
   - Match quality scores
   - Product details (GTIN, brand, format, etc.)
4. Ask Claude: **"Show me the comparison file"** to view a summary

### Excel Report Columns

The comparison Excel file contains 18 columns:

1. **GTIN** - Universal product code
2. **Source Code** - Your supplier's product code
3. **Product Name**
4. **Brand**
5. **Format** - Product size
6. **Packaging**
7. **Category**
8. **Source Price** - Price from your invoice
9. **Quantity**
10. **Line Total**
11. **Old Target Price** - Last known price from database (reference only)
12. **New Target Price** - Empty column for you to fill in current prices
13. **Match Type** - Exact/Fuzzy/No Match
14. **Similarity %** - Match confidence (0-100%)
15. **Target Code** - Colabor's product code
16. **Target Product** - Colabor's product name
17. **Target Brand**
18. **Target Format**

**Color Coding:**
- 🟢 Green = Exact match (100%)
- 🟡 Yellow = Fuzzy match (60-99%)
- 🔴 Red = No match found

**Price Columns Explained:**
- **Old Target Price**: Shows the last price we have in the database. This is for reference - don't edit this column.
- **New Target Price**: Leave this blank in the exported file. Fill it in with current market prices, then re-import to update the database.

### Adding Corrections and Updating Prices

When you find better matches, new products, or updated prices:

1. Open the comparison Excel file
2. Add/edit:
   - GTIN (if you have it)
   - Target Code (correct supplier code)
   - **New Target Price** (fill in current prices - they change frequently!)
   - **Source Price** (if different from invoice)
   - Any other product information
3. Upload the Excel back to Claude
4. Say: **"Import these corrections"**

The system will:
- Create new products in the database
- Add supplier code mappings
- **Update prices** from the "New Target Price" column
- Track when prices were last updated (`price_updated_at`)
- Use corrections and updated prices in future comparisons

**Price Update Workflow:**

Prices change frequently, so we use an "Old/New" pattern:

1. **First export**:
   - "Old Target Price" shows last known price (or blank if new product)
   - "New Target Price" is empty

2. **You fill in**:
   - Enter current market prices in "New Target Price" column
   - Leave "Old Target Price" as-is (reference only)

3. **Import back**:
   - System reads "New Target Price" column and updates database
   - Timestamps the update

4. **Next export**:
   - Your prices now appear in "Old Target Price"
   - "New Target Price" is empty again (ready for next update cycle)

This pattern prevents accidental overwrites and gives you a clear before/after view of price changes.

### View Comparison Files

After running comparisons, you can ask Claude to analyze the Excel files:

```
"Show me the comparison file"
"List all comparison files"
"What were the results from my last comparison?"
```

Claude will read the Excel file and provide a summary with:
- Match statistics (exact, fuzzy, no match)
- Sample products
- Overall comparison quality

### Search Products

```
"Find Iogo vanilla yogurt at Colabor"
"Search for Cheerios cereal"
"Tell me about product code 325141 at Dubé Loiselle"
```

## Command-Line Tools

The package includes command-line utilities:

### Import Excel to Database

```bash
uvx --from invoice-comparison-mcp invoice-comparison-import products.xlsx
```

Supports flexible column detection:
- GTIN (required)
- Product Name (required)
- Brand, Format, Packaging, Category (optional)
- Supplier code columns (e.g., "Colabor Code", "Mayrand Code")

### Merge Databases

Combine multiple databases (e.g., from different users):

```bash
uvx --from invoice-comparison-mcp invoice-comparison-merge database1.db database2.db merged.db
```

## File Locations

- **Database**: `~/.invoice-comparison/supplier_mappings.db`
- **Excel Reports**: `~/Downloads/invoice_comparison_*.xlsx`
- **Demo Database**: Included with package (100 products)
- **Full Database**: Download separately (41,898 products, ~11 MB)

### Backup Your Database

```bash
cp ~/.invoice-comparison/supplier_mappings.db ~/.invoice-comparison/backup_$(date +%Y%m%d).db
```

## Development

### Local Installation

```bash
# Clone the repository
git clone https://github.com/mhosaic-technologies/invoice-comparison-mcp.git
cd invoice-comparison-mcp

# Install in development mode
pip install -e .

# Run tests
pytest
```

### Project Structure

```
invoice-comparison-mcp/
├── src/
│   └── invoice_comparison/
│       ├── __init__.py
│       ├── mcp_server.py           # MCP server entry point
│       ├── comparison_engine.py    # Comparison logic and Excel generation
│       ├── database/               # Database models and operations
│       ├── matching/               # Product matching algorithms
│       ├── tools/                  # Command-line utilities
│       └── data/
│           └── demo_database.db    # Sample database
├── pyproject.toml                  # Package configuration
└── README.md
```

## Supported Suppliers

- **Colabor**
- **Mayrand**
- **Dubé Loiselle**
- **FLB**
- **Ben Deshaies**
- **GFS**

Additional suppliers can be added through the database.

## Requirements

- **Python**: 3.9 or later
- **Claude Desktop**: Latest version
- **Operating System**: macOS 10.15+ or Windows 10+

## Troubleshooting

### MCP Server Not Responding

1. Quit Claude Desktop completely (Cmd+Q on Mac)
2. Reopen Claude Desktop
3. Check that tools are available

### Database Not Found

The database initializes automatically on first run. If you have issues:

```bash
# Check if database exists
ls -la ~/.invoice-comparison/

# Manually initialize
uvx --from invoice-comparison-mcp invoice-comparison-server
```

### Import Errors

If imports fail:
- Verify Excel file has GTIN and Product Name columns
- Check column names (case-insensitive, flexible matching)
- Ensure supplier code columns are named clearly (e.g., "Colabor Code")

## Privacy & Data

- All processing happens locally on your computer
- Database stored in your home directory
- No telemetry or tracking
- Only Claude AI service is used (for invoice parsing)

## License

MIT License - See LICENSE file for details

## Support

- **Issues**: https://github.com/mhosaic-technologies/invoice-comparison-mcp/issues
- **Documentation**: This README and inline documentation

## Credits

**Developed for**: William Coop  
**Powered by**: Claude AI (Anthropic)  
**MCP Protocol**: https://github.com/anthropics/mcp

---

**Ready to compare invoices? Open Claude Desktop and drag in an invoice!**
