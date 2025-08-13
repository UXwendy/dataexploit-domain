"""Models for organizations search tool."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from ..base.models import BaseSearchInput


class OrganizationsSearchInput(BaseSearchInput):
    """Input schema for organizations search."""
    
    # Organization-specific filters
    country: Optional[str] = Field(
        default=None,
        description="""Filter by country. Optional.
        
        Example: "Sweden", "United States", "Germany"
        """
    )
    
    city: Optional[str] = Field(
        default=None,
        description="""Filter by city. Optional.
        
        Example: "Gothenburg", "Stockholm", "London"
        """
    )
    
    organization_type: Optional[str] = Field(
        default=None,
        description="""Filter by organization type. Optional.
        
        Common types: "University", "Company", "Private", "Government"
        """
    )
    
    active_only: bool = Field(
        default=True,
        description="""Only return active organizations. Default: True.
        
        Set to false to include inactive/historical organizations.
        """
    )
    
    has_coordinates: Optional[bool] = Field(
        default=None,
        description="""Filter to organizations with geographic coordinates. Optional.
        
        Useful for mapping applications.
        """
    )


class OrganizationStandard(BaseModel):
    """Standard organization fields - minimal."""
    id: str
    display_name: str  # English name
    country: Optional[str] = None
    city: Optional[str] = None
    organization_type: Optional[str] = None  # Primary type
    is_active: bool
    level: int  # Hierarchy level
    score: Optional[float] = None


class OrganizationExpanded(OrganizationStandard):
    """Expanded organization fields - includes path and coordinates."""
    display_path: Optional[str] = None  # Full hierarchical path
    parent_id: Optional[str] = None
    parent_name: Optional[str] = None
    geo_lat: Optional[float] = None
    geo_long: Optional[float] = None
    organization_types: List[str] = []  # All types
    child_count: int = 0


class OrganizationFull(OrganizationExpanded):
    """Full organization fields - complete record."""
    name_swe: Optional[str] = None
    display_name_swe: Optional[str] = None
    display_path_swe: Optional[str] = None
    identifiers: List[Dict[str, Any]] = []
    organization_parents: List[Dict[str, Any]] = []
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    validated_by: Optional[str] = None
    validated_date: Optional[str] = None