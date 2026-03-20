"""NetFile Campaign Finance MCP Server.

Provides MCP tools for querying California local campaign finance data
via the NetFile Connect2 public API. No authentication required.
"""

from .server import mcp

__all__ = ["mcp"]
