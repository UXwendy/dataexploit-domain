"""Models for persons search tool."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from ..base.models import BaseSearchInput


class PersonsSearchInput(BaseSearchInput):
    """Input schema for persons search.
    
    CRITICAL: The 'query' field searches ONLY person names, not research topics!
    - Correct: query="John Doe" or query="Smith"
    - Wrong: query="machine learning" (will return 0 results)
    """
    
    # Override query field description from base
    query: str = Field(
        description="""Search for person names ONLY. Required field.
        
        CORRECT EXAMPLES:
        - "John Doe" - finds specific person
        - "Smith" - finds all people with Smith in their name
        - "" - empty string to list all (use with filters)
        
        INCORRECT EXAMPLES:
        - "quantum computing" - This is a topic, not a name! Use search_publications instead
        - "AI researchers" - This is a field, not a name! Use search_publications instead
        
        TO FIND RESEARCHERS BY FIELD:
        1. Use search_publications(query="quantum computing")
        2. Extract author names from results
        3. Then use search_persons(query="Author Name") for details
        """
    )
    
    # Person-specific filters
    organization: Optional[str] = Field(
        default=None,
        description="""Filter by organization name. Optional.
        
        Example: "Chalmers", "Computer Science", "Physics"
        
        NOTE: This searches in the person's affiliated organizations.
        """
    )
    
    has_orcid: Optional[bool] = Field(
        default=None,
        description="""Filter to only people with ORCID identifiers. Optional.
        
        Set to true to find researchers with ORCID IDs.
        """
    )
    
    has_publications: Optional[bool] = Field(
        default=None,
        description="""Filter to only people with publications. Optional.
        
        Set to true to find active researchers with publications.
        """
    )
    
    active_only: bool = Field(
        default=True,
        description="""Only return active researchers. Default: True.
        
        Set to false to include inactive/historical researchers.
        """
    )


class PersonStandard(BaseModel):
    """Standard person fields - minimal."""
    id: str
    display_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: bool
    has_publications: bool
    has_orcid: bool
    score: Optional[float] = None


class PersonExpanded(PersonStandard):
    """Expanded person fields - includes identifiers and affiliations."""
    orcid: Optional[str] = None
    scopus_id: Optional[str] = None
    organization_names: List[str] = []
    organization_count: int = 0
    has_projects: bool = False


class PersonFull(PersonExpanded):
    """Full person fields - complete record."""
    identifiers: List[Dict[str, Any]] = []
    organizations: List[Dict[str, Any]] = []
    pdb_categories: List[str] = []
    birth_year: Optional[int] = None
    created_at: Optional[str] = None
    created_by: Optional[str] = None