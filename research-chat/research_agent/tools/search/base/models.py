"""Base models shared across all search tools."""
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class FieldSelection(str, Enum):
    """Field selection levels for all tools."""
    STANDARD = "standard"      # Default - fast, minimal fields
    EXPANDED = "expanded"      # More fields - use when you need abstracts/details  
    FULL = "full"             # All fields - AVOID unless absolutely necessary


class SortBy(str, Enum):
    """Sort options for all tools."""
    RELEVANCE = "relevance"    # Default for all tools
    DATE_DESC = "date_desc"    # Newest first
    DATE_ASC = "date_asc"      # Oldest first
    NAME_ASC = "name_asc"      # Alphabetical
    # Aliases for intuitive use
    YEAR_DESC = "date_desc"    # Alias for date_desc (newest first)
    YEAR_ASC = "date_asc"      # Alias for date_asc (oldest first)


class BaseSearchInput(BaseModel):
    """Base schema for all search tools."""
    
    model_config = ConfigDict(use_enum_values=True)
    
    query: str = Field(
        default="",
        description="""The search query. Default: empty string.
        
        Examples:
        - "machine learning"
        - "John Doe"  
        - "quantum computing"
        
        For empty searches (e.g., list all with filters), use an empty string: ""
        """
    )
    
    max_results: int = Field(
        default=10,
        ge=1,
        le=100,
        description="""Maximum results to return. Default: 10.
        
        IMPORTANT: Start with the default. Only increase if you specifically need more results.
        Requesting too many results will slow down the response.
        """
    )
    
    offset: int = Field(
        default=0,
        ge=0,
        description="""Offset for pagination. Default: 0.
        
        Use this with max_results to page through results.
        Example: offset=20, max_results=10 returns results 21-30.
        """
    )
    
    sort_by: SortBy = Field(
        default=SortBy.RELEVANCE,
        description="""Sort order. Default: "relevance".
        
        Only change this if you specifically need chronological or alphabetical ordering.
        Options: relevance, date_desc, date_asc, name_asc
        """
    )
    
    field_selection: FieldSelection = Field(
        default=FieldSelection.STANDARD,
        description="""Field selection level. Default: "standard".
        
        IMPORTANT: Use "standard" for most queries. It's fast and contains essential information.
        
        - "standard": Minimal fields for quick results (RECOMMENDED)
        - "expanded": Includes abstracts and more details (only if needed)  
        - "full": Complete records (SLOW - avoid unless required for analysis)
        
        DO NOT use "expanded" or "full" unless you specifically need the extra fields.
        """
    )


class SearchResult(BaseModel):
    """Base search result structure."""
    results: List[Dict[str, Any]]
    pagination: Dict[str, Any]
    query: str
    filters_applied: Dict[str, Any]
    sort_by: str
    field_selection: str
    search_time_ms: Optional[int] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    facets: Optional[Dict[str, List[Dict[str, Any]]]] = None