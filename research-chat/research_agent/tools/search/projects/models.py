"""Models for projects search tool."""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

from ..base.models import BaseSearchInput


class ProjectsSearchInput(BaseSearchInput):
    """Input schema for projects search."""
    
    # Project-specific filters
    start_year: Optional[int] = Field(
        default=None,
        ge=1900,
        le=2100,
        description="""Filter by project start year (inclusive). Optional.
        
        Example: 2020 to find projects starting in 2020 or later.
        """
    )
    
    end_year: Optional[int] = Field(
        default=None,
        ge=1900,
        le=2100,
        description="""Filter by project end year (inclusive). Optional.
        
        Example: 2025 to find projects ending by 2025.
        """
    )
    
    status: Optional[str] = Field(
        default=None,
        description="""Filter by project status. Optional.
        
        Options:
        - "active": Currently running projects
        - "completed": Finished projects
        - "upcoming": Future projects
        
        If not specified, returns all projects.
        """
    )
    
    min_funding: Optional[float] = Field(
        default=None,
        ge=0,
        description="""Minimum funding amount in SEK. Optional.
        
        Example: 1000000 for projects with at least 1M SEK funding.
        """
    )
    
    funder: Optional[str] = Field(
        default=None,
        description="""Filter by funding organization name. Optional.
        
        Example: "VINNOVA", "Vetenskapsrådet", "EU"
        """
    )
    
    organization: Optional[str] = Field(
        default=None,
        description="""Filter by participating organization/department. Optional.
        
        Examples:
        - Department: "Electrical Engineering", "Computer Science and Engineering"
        - Abbreviation: "CSE", "EE" (will be mapped automatically)
        - Unit: "Electric Power Engineering", "Automatic Control"
        
        Filters projects where this organization is involved.
        """
    )
    
    pi_name: Optional[str] = Field(
        default=None,
        description="""Filter by Principal Investigator (Project Manager) name. Optional.
        
        Example: "John Doe"
        
        Searches for projects where this person is the PI/Project Manager.
        """
    )
    
    include_facets: Optional[List[str]] = Field(
        default=None,
        description="""Include aggregated counts for specified fields. Optional.
        
        Available facets:
        - "funders": Top funding organizations
        - "organizations": Top participating organizations
        - "years": Project start years distribution
        - "status": Project status distribution (active/completed/upcoming)
        - "pis": Top Principal Investigators
        
        Example: ["funders", "years"] returns top funders and yearly distribution.
        Maximum 20 items returned per facet.
        """
    )
    
    facet_size: Optional[int] = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of items to return per facet (default: 20, max: 100)"
    )
    
    @field_validator('status')
    def validate_status(cls, v):
        """Validate status value."""
        if v and v not in ['active', 'completed', 'upcoming']:
            raise ValueError('Status must be "active", "completed", or "upcoming"')
        return v


class ProjectStandard(BaseModel):
    """Standard project fields - minimal."""
    id: int
    title: str  # Will use English title
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: str  # computed: active/completed/upcoming
    total_funding: Optional[float] = None
    currency: Optional[str] = None
    pi_name: Optional[str] = None  # Principal Investigator
    score: Optional[float] = None


class ProjectExpanded(ProjectStandard):
    """Expanded project fields - includes description and participants."""
    description: Optional[str] = None  # Plain text, truncated
    funder_names: List[str] = []
    participant_count: int = 0
    participant_names: List[str] = []  # First 10 participants
    organization_count: int = 0


class ProjectFull(ProjectExpanded):
    """Full project fields - complete record."""
    description_full: Optional[str] = None  # Complete description
    title_swe: Optional[str] = None
    description_swe: Optional[str] = None
    contracts: List[Dict[str, Any]] = []
    persons: List[Dict[str, Any]] = []
    organizations: List[Dict[str, Any]] = []
    keywords: List[str] = []
    categories: List[Dict[str, Any]] = []