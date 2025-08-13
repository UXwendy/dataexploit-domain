# Research Tools

Drop-in replacement for research_agent tools with enhanced search capabilities.

## Quick Start

1. Ensure environment variables are set:
   ```
   ES_HOST=https://your-elasticsearch-host:9200
   ES_USER=your-username
   ES_PASS=your-password
   ES_INDEX=research-publications-static
   ```

2. Import and use:
   ```python
   from tools import get_all_tools
   
   # Get all available tools
   tools = get_all_tools()
   
   # Use with LangChain agent
   agent = initialize_agent(tools, llm, ...)
   ```

## Available Tools

### UnifiedSearchTool
Advanced search tool for research publications with:
- Multi-field search (title, abstract, authors, keywords)
- Comprehensive filtering (years, authors, publication types, etc.)
- Smart field selection to minimize data transfer
- Pagination support
- Multiple sort options

## Requirements

See `requirements-tools.txt` for minimal dependencies.

## Structure

```
tools/
├── __init__.py          # Main entry point
├── config/              # Configuration management
├── utils/               # Utility functions
└── search/              # Search tools
    ├── models/          # Pydantic models
    ├── query_builders/  # Elasticsearch query builders
    └── unified_search.py # Main search tool
```