"""Models for publications search tool."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from ..base.models import BaseSearchInput


class PublicationsSearchInput(BaseSearchInput):
    """Input schema for publications search.
    
    PRIMARY TOOL: Use this FIRST for any research topic queries!
    """
    
    # Override query field to emphasize this is the main research tool
    query: str = Field(
        default="",
        description="""Search for research topics, keywords, or paper titles. Default: empty string.
        
        THIS IS YOUR MAIN RESEARCH TOOL! Use for:
        - Research topics: "quantum computing", "machine learning", "sustainability"
        - Specific papers: "neural networks for image recognition"
        - Research areas: "autonomous vehicles", "AI in healthcare"
        - Empty string "" to list all (use with filters like authors, year, organization)
        
        TO FIND LEADING RESEARCHERS:
        1. search_publications(query="quantum computing", max_results=20-30)
        2. Analyze author frequency in results
        3. Use search_persons(query="Author Name") for researcher details
        """
    )
    
    # Publication-specific filters
    authors: Optional[List[str]] = Field(
        default=None,
        description="""Filter by SPECIFIC author names. Optional.
        
        Example: ["John Doe", "Jane Smith"]
        
        Use when you know exact author names. For finding researchers by field,
        use the query parameter instead and analyze results.
        """
    )
    
    year_from: Optional[int] = Field(
        default=None,
        ge=1900,
        le=2100,
        description="Filter by start year (inclusive). Optional."
    )
    
    year_to: Optional[int] = Field(
        default=None,
        ge=1900,
        le=2100,
        description="Filter by end year (inclusive). Optional."
    )
    
    publication_types: Optional[List[str]] = Field(
        default=None,
        description="""Filter by publication type. Optional.
        
        Common types: "Journal article", "Conference paper", "Book chapter", "Thesis"
        """
    )
    
    keywords: Optional[List[str]] = Field(
        default=None,
        description="""Filter by keywords. Optional.
        
        Example: ["machine learning", "neural networks"]
        """
    )
    
    source: Optional[str] = Field(
        default=None,
        description="""Filter by publication source/journal. Optional.
        
        Example: "Nature", "Science", "IEEE"
        """
    )
    
    organization: Optional[str] = Field(
        default=None,
        description="""Filter by author organization/department. Optional.
        
        Examples:
        - Department: "Electrical Engineering", "Computer Science and Engineering"
        - Abbreviation: "CSE", "EE" (will be mapped automatically)
        - Unit: "Electric Power Engineering", "Automatic Control"
        
        Filters publications where at least one author is affiliated with this organization.
        """
    )
    
    include_facets: Optional[List[str]] = Field(
        default=None,
        description="""Include aggregated counts for specified fields. Optional.
        
        Available facets:
        - "authors": Top authors by publication count
        - "organizations": Top organizations by publication count
        - "years": Publication count by year
        - "types": Publication types distribution
        - "keywords": Most common keywords
        
        Example: ["authors", "years"] returns top authors and yearly distribution.
        Maximum 20 items returned per facet.
        """
    )
    
    facet_size: Optional[int] = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of items to return per facet (default: 20, max: 100)"
    )


class PublicationStandard(BaseModel):
    """Standard publication fields - minimal."""
    id: str
    title: str
    year: Optional[int] = None
    publication_type: Optional[str] = None
    source_title: Optional[str] = None
    author_names: List[str] = []  # Simple list of names
    author_count: int = 0
    score: Optional[float] = None


class PublicationExpanded(PublicationStandard):
    """Expanded publication fields - includes abstract and identifiers."""
    abstract: Optional[str] = None  # Truncated
    keywords: List[str] = []
    doi: Optional[str] = None
    scopus_id: Optional[str] = None
    authors: List[Dict[str, Any]] = []  # Structured author info
    source: Optional[Dict[str, Any]] = None  # Source details
    is_open_access: bool = False
    language: Optional[str] = None


class PublicationFull(PublicationExpanded):
    """Full publication fields - complete record."""
    abstract_full: Optional[str] = None  # Complete abstract
    all_identifiers: Dict[str, List[str]] = {}  # All ID types
    persons: List[Dict[str, Any]] = []  # Full person data (limited)
    organizations: List[Dict[str, Any]] = []
    categories: List[Dict[str, Any]] = []
    data_objects: List[Dict[str, Any]] = []  # URLs and files
    details_url_eng: Optional[str] = None
    details_url_swe: Optional[str] = None