# NetFile Campaign Finance MCP Server

An MCP (Model Context Protocol) server that provides access to California local campaign finance data via the [NetFile Connect2 API](https://netfile.com/Connect2/api/). No authentication required — all data is public.

Covers **~220 agencies** across California, including cities, counties, and special districts that use NetFile for campaign finance e-filing.

## Installation

### Claude Desktop / Claude Chat

Add to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "netfile": {
      "command": "uvx",
      "args": ["netfile-mcp"]
    }
  }
}
```

Or install from source:

```json
{
  "mcpServers": {
    "netfile": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mcp/netfile", "netfile-mcp"]
    }
  }
}
```

### Claude Code

Add a `.mcp.json` to your project root:

```json
{
  "mcpServers": {
    "netfile": {
      "command": "uvx",
      "args": ["netfile-mcp"]
    }
  }
}
```

### pip install

```bash
pip install netfile-mcp
```

## Available Tools

### `search_contributions`

Search campaign finance contributions for any NetFile agency.

```
Search contributions in Richmond CA from 2024 onward
```

**Parameters:**
- `city` — City or agency name (e.g. "Richmond", "San Francisco")
- `agency_id` — NetFile agency ID (alternative to city name)
- `date_start` / `date_end` — Date range filter (YYYY-MM-DD)
- `amount_min` / `amount_max` — Amount range filter
- `query` — Free-text search (names, employers, etc.)
- `transaction_type` — FPPC type code (0=monetary, 1=non-monetary, etc.)
- `include_expenditures` — Also fetch expenditure records
- `limit` — Max results to return (default 100; summary stats always reflect full dataset)

### `lookup_city`

Find a city's NetFile agency ID by name or shortcut code.

```
Look up San Francisco in NetFile
```

### `list_agencies`

List all ~220 agencies that use NetFile.

### `get_committee_info`

Get campaign committees registered with an agency (names, FPPC IDs).

### `list_transaction_types`

Reference for FPPC transaction type codes.

## Examples

**"Who are the top donors to Richmond, CA city council candidates?"**
→ Uses `search_contributions` with `city="Richmond"`, then analyzes by contributor name.

**"What California cities use NetFile for campaign finance?"**
→ Uses `list_agencies` to see all available agencies.

**"Show me contributions over $1,000 to Oakland committees since 2023"**
→ Uses `search_contributions` with `city="Oakland"`, `amount_min=1000`, `date_start="2023-01-01"`.

## Data Source

All data comes from the [NetFile Connect2 public API](https://netfile.com/Connect2/api/). NetFile is the e-filing platform used by many California local agencies for campaign finance disclosure under the Political Reform Act (FPPC).

- **No authentication required** — the API is fully public
- **No rate limit keys** — built-in 0.5s delay between requests
- **Retry logic** — handles NetFile's intermittent HTTP 500 errors with exponential backoff
- **Deduplication** — automatically handles amended filing duplicates

## Development

```bash
cd mcp/netfile
pip install -e .
pytest tests/ -v
```

## License

MIT

Built by [Richmond Common](https://github.com/phillipgarland/richmond-transparency-project) — local government accountability infrastructure.
