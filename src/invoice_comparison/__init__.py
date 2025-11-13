"""
Invoice Comparison MCP Server

Compare supplier invoices using AI to find equivalent products and make
informed purchasing decisions.
"""

__version__ = "1.0.0"
__author__ = "Your Company"

from .mcp_server import main
from .comparison_engine import ComparisonEngine

__all__ = ["main", "ComparisonEngine"]
