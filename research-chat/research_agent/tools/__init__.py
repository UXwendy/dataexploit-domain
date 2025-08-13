"""Research tools package - drop-in replacement for research_agent tools."""

from .search.registry import get_all_tools

__all__ = ['get_all_tools']