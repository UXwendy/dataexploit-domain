"""Organizations search tool implementation."""
from typing import Dict, Any, List, Optional, Type

from ..base.elasticsearch_tool import BaseElasticsearchSearchTool
from .models import OrganizationsSearchInput, OrganizationStandard, OrganizationExpanded, OrganizationFull


class OrganizationsSearchTool(BaseElasticsearchSearchTool):
    """Search tool for organizations."""
    
    name: str = "search_organizations"
    description: str = """Search for organizations (universities, companies, institutions) in the academic database.
    
    CAPABILITIES:
    - Find organizations by name or location
    - Filter by country, city, or organization type
    - Get hierarchical organization structures
    - Access geographic coordinates for mapping
    
    USE CASES:
    - Find universities: search_organizations(query="University", organization_type="University")
    - Find by location: search_organizations(query="", country="Sweden", city="Gothenburg")
    - Find specific org: search_organizations(query="Chalmers")
    - Get all with coordinates: search_organizations(query="", has_coordinates=true)
    
    DO NOT USE THIS TOOL FOR:
    - Finding publications (use search_publications)
    - Finding researcher profiles (use search_persons)
    - Finding projects (use search_projects)
    
    LIMITATIONS:
    - Cannot count members or publications per organization
    - Cannot aggregate statistics across organizations
    
    BEST PRACTICES:
    - Start with max_results=5-10 for initial searches
    - Only use field_selection="expanded" if you need full paths and coordinates
    
    RETURNS: List of organizations, each containing:
    - Standard: (id, display_name_eng, display_name_swe, organization_type, country, city, has_coordinates, score)
    - Expanded: + (name_eng, name_swe, path_eng, path_swe, level, parent_id, latitude, longitude)
    - Full: + (all_names, hierarchical_structure, contact_info, external_links)
    """
    
    args_schema: Type[OrganizationsSearchInput] = OrganizationsSearchInput
    
    def _build_search_request(
        self,
        query: str,
        max_results: int,
        offset: int,
        sort_by: str,
        field_selection: str,
        filters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build Elasticsearch query for organizations."""
        
        # Start with base query structure
        es_query = {
            "size": max_results,
            "from": offset
        }
        
        # Build query clauses
        must_clauses = []
        filter_clauses = []
        
        # Main query - search in name fields
        if query:
            must_clauses.append({
                "multi_match": {
                    "query": query,
                    "fields": [
                        "DisplayNameEng^3",
                        "DisplayNameSwe^2",
                        "NameEng^2",
                        "NameSwe",
                        "DisplayPathEng",
                        "City"
                    ],
                    "type": "best_fields"
                }
            })
        
        # Apply filters
        if filters.get('active_only', True):
            filter_clauses.append({"term": {"IsActive": True}})
        
        if filters.get('country'):
            filter_clauses.append({
                "match": {"Country": filters['country']}
            })
        
        if filters.get('city'):
            filter_clauses.append({
                "match": {"City": filters['city']}
            })
        
        if filters.get('organization_type'):
            filter_clauses.append({
                "bool": {
                    "should": [
                        {"match": {"OrganizationTypes.NameEng": filters['organization_type']}},
                        {"match": {"OrganizationTypes.NameSwe": filters['organization_type']}}
                    ],
                    "minimum_should_match": 1
                }
            })
        
        if filters.get('has_coordinates') is not None:
            if filters['has_coordinates']:
                filter_clauses.extend([
                    {"exists": {"field": "GeoLat"}},
                    {"exists": {"field": "GeoLong"}}
                ])
            else:
                filter_clauses.append({
                    "bool": {
                        "must_not": [
                            {"exists": {"field": "GeoLat"}},
                            {"exists": {"field": "GeoLong"}}
                        ]
                    }
                })
        
        # Construct the bool query
        bool_query = {}
        if must_clauses:
            bool_query["must"] = must_clauses
        if filter_clauses:
            bool_query["filter"] = filter_clauses
        
        # Set the query
        if bool_query:
            es_query["query"] = {"bool": bool_query}
        else:
            es_query["query"] = {"match_all": {}}
        
        # Add sorting
        es_query["sort"] = self._build_sort_clause(sort_by)
        
        # Add source filtering for optimization
        source_fields = self._get_source_fields(field_selection)
        if source_fields:
            es_query["_source"] = source_fields
        
        return es_query
    
    def _build_sort_clause(self, sort_by: str) -> List[Dict[str, Any]]:
        """Build sort clause specific to organizations."""
        if sort_by == "relevance":
            return ["_score", {"DisplayNameEng.keyword": "asc"}]
        elif sort_by == "name_asc":
            return [{"DisplayNameEng.keyword": "asc"}]
        elif sort_by == "date_desc":
            # Sort by creation/update date if available
            return [{"UpdatedAt": "desc"}, {"DisplayNameEng.keyword": "asc"}]
        elif sort_by == "date_asc":
            return [{"UpdatedAt": "asc"}, {"DisplayNameEng.keyword": "asc"}]
        else:
            return ["_score"]
    
    def _get_source_fields(self, field_selection: str) -> Optional[List[str]]:
        """Get source fields to retrieve based on selection level."""
        if field_selection == "standard":
            return [
                "Id", "DisplayNameEng", "DisplayNameSwe",
                "Country", "City", "OrganizationTypes",
                "IsActive", "Level"
            ]
        elif field_selection == "expanded":
            return [
                "Id", "DisplayNameEng", "DisplayNameSwe",
                "DisplayPathEng", "DisplayPathSwe",
                "Country", "City", "GeoLat", "GeoLong",
                "OrganizationTypes", "OrganizationParents",
                "IsActive", "Level"
            ]
        else:
            # Full - return everything except maintenance fields
            return None
    
    def _transform_results(
        self,
        raw_results: Dict[str, Any],
        field_selection: str
    ) -> List[Dict[str, Any]]:
        """Transform raw results based on field selection."""
        
        transformed = []
        
        for hit in raw_results['hits']['hits']:
            doc = hit.get('_source')
            if not doc:
                continue
            score = hit.get('_score')
            
            # Extract primary organization type
            org_type = None
            if doc.get('OrganizationTypes'):
                org_type = doc['OrganizationTypes'][0].get('NameEng') if doc['OrganizationTypes'] else None
            
            if field_selection == "standard":
                # Minimal fields
                org = OrganizationStandard(
                    id=doc['Id'],
                    display_name=doc.get('DisplayNameEng') or doc.get('DisplayNameSwe', 'Unknown'),
                    country=doc.get('Country'),
                    city=doc.get('City'),
                    organization_type=org_type,
                    is_active=doc.get('IsActive', False),
                    level=doc.get('Level', 0),
                    score=score
                )
                transformed.append(org.model_dump())
                
            elif field_selection == "expanded":
                # Include path and coordinates
                # Extract parent info
                parent_id = None
                parent_name = None
                if doc.get('OrganizationParents'):
                    parent = doc['OrganizationParents'][0] if doc['OrganizationParents'] else None
                    if parent:
                        parent_id = parent.get('Id')
                        parent_name = parent.get('DisplayNameEng') or parent.get('NameEng')
                
                # Extract all organization types
                org_types = []
                if doc.get('OrganizationTypes'):
                    org_types = [
                        t.get('NameEng') or t.get('NameSwe') 
                        for t in doc['OrganizationTypes'] 
                        if t.get('NameEng') or t.get('NameSwe')
                    ]
                
                # Convert coordinates
                geo_lat = None
                geo_long = None
                if doc.get('GeoLat') and doc.get('GeoLong'):
                    try:
                        geo_lat = float(doc['GeoLat'])
                        geo_long = float(doc['GeoLong'])
                    except:
                        pass
                
                org = OrganizationExpanded(
                    id=doc['Id'],
                    display_name=doc.get('DisplayNameEng') or doc.get('DisplayNameSwe', 'Unknown'),
                    country=doc.get('Country'),
                    city=doc.get('City'),
                    organization_type=org_type,
                    is_active=doc.get('IsActive', False),
                    level=doc.get('Level', 0),
                    score=score,
                    display_path=doc.get('DisplayPathEng'),
                    parent_id=parent_id,
                    parent_name=parent_name,
                    geo_lat=geo_lat,
                    geo_long=geo_long,
                    organization_types=org_types,
                    child_count=0  # Would need aggregation to get this
                )
                transformed.append(org.model_dump())
                
            else:  # full
                # Return most fields but clean up maintenance fields
                full_doc = {
                    'id': doc['Id'],
                    'display_name': doc.get('DisplayNameEng') or doc.get('DisplayNameSwe', 'Unknown'),
                    'display_name_swe': doc.get('DisplayNameSwe'),
                    'name_swe': doc.get('NameSwe'),
                    'country': doc.get('Country'),
                    'city': doc.get('City'),
                    'organization_type': org_type,
                    'is_active': doc.get('IsActive', False),
                    'level': doc.get('Level', 0),
                    'score': score,
                    'display_path': doc.get('DisplayPathEng'),
                    'display_path_swe': doc.get('DisplayPathSwe'),
                    'geo_lat': float(doc['GeoLat']) if doc.get('GeoLat') else None,
                    'geo_long': float(doc['GeoLong']) if doc.get('GeoLong') else None,
                    'identifiers': doc.get('Identifiers', []),
                    'organization_parents': doc.get('OrganizationParents', []),
                    'organization_types': doc.get('OrganizationTypes', []),
                    'start_year': doc.get('StartYear') if doc.get('StartYear', 0) > 0 else None,
                    'end_year': doc.get('EndYear') if doc.get('EndYear', 0) > 0 else None,
                    'validated_by': doc.get('ValidatedBy'),
                    'validated_date': doc.get('ValidatedDate')
                }
                transformed.append(full_doc)
        
        return transformed