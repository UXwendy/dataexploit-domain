"""Persons search tool implementation."""
from typing import Dict, Any, List, Optional, Type
import re

from ..base.elasticsearch_tool import BaseElasticsearchSearchTool
from .models import PersonsSearchInput, PersonStandard, PersonExpanded, PersonFull


class PersonsSearchTool(BaseElasticsearchSearchTool):
    """Search tool for researcher profiles."""
    
    name: str = "search_persons"
    description: str = """Search for researchers by name in the Chalmers academic database.
    
    This tool searches ONLY by person names, NOT by research topics or expertise areas.
    For finding researchers in specific fields, use search_publications first to identify authors.
    
    The tool automatically handles name variations, special characters, and different formats.
    
    Input should be a person's name or use filters for department-wide searches.
    """
    
    args_schema: Type[PersonsSearchInput] = PersonsSearchInput
    
    def _normalize_name(self, name: str) -> List[str]:
        """Generate name variants for searching."""
        variants = [name]
        
        # Handle special Nordic characters
        nordic_replacements = {
            'ä': 'a', 'Ä': 'A',
            'ö': 'o', 'Ö': 'O', 
            'å': 'a', 'Å': 'A',
            'æ': 'ae', 'Æ': 'AE',
            'ø': 'o', 'Ø': 'O'
        }
        
        # Create variant without special characters
        normalized = name
        for old, new in nordic_replacements.items():
            normalized = normalized.replace(old, new)
        if normalized != name:
            variants.append(normalized)
        
        # Handle hyphens
        if '-' in name:
            variants.append(name.replace('-', ' '))
            variants.append(name.replace('-', ''))
        
        # Try last name first format if it looks like a full name
        parts = name.split()
        if len(parts) >= 2:
            # Standard "Last, First" format
            variants.append(f"{parts[-1]}, {' '.join(parts[:-1])}")
            # Also try "Last First" without comma
            variants.append(f"{parts[-1]} {' '.join(parts[:-1])}")
        
        return list(set(variants))  # Remove duplicates
    
    def _build_person_query(self, query: str) -> Dict[str, Any]:
        """Build multi-strategy person name query."""
        strategies = []
        
        # Strategy 1: Full name search with fuzzy matching
        strategies.append({
            "multi_match": {
                "query": query,
                "fields": ["DisplayName^3", "DisplayName.keyword^5"],
                "type": "best_fields",
                "fuzziness": "AUTO",
                "prefix_length": 2
            }
        })
        
        # Strategy 2: Traditional multi-match with OR
        strategies.append({
            "multi_match": {
                "query": query,
                "fields": [
                    "DisplayName^3",
                    "FirstName^2", 
                    "LastName^2"
                ],
                "type": "best_fields",
                "operator": "or",
                "minimum_should_match": "75%"
            }
        })
        
        # Strategy 3: Parse name and search components
        parts = query.split()
        if len(parts) >= 2:
            # Try matching first and last name separately
            strategies.append({
                "bool": {
                    "should": [
                        # First Last order
                        {
                            "bool": {
                                "must": [
                                    {"match": {"FirstName": " ".join(parts[:-1])}},
                                    {"match": {"LastName": parts[-1]}}
                                ]
                            }
                        },
                        # Last First order
                        {
                            "bool": {
                                "must": [
                                    {"match": {"LastName": parts[0]}},
                                    {"match": {"FirstName": " ".join(parts[1:])}}
                                ]
                            }
                        }
                    ]
                }
            })
        
        # Strategy 4: Try name variants
        name_variants = self._normalize_name(query)
        if len(name_variants) > 1:
            for variant in name_variants[1:]:  # Skip original
                strategies.append({
                    "multi_match": {
                        "query": variant,
                        "fields": ["DisplayName^2", "DisplayName.keyword^3"],
                        "type": "best_fields"
                    }
                })
        
        return {"bool": {"should": strategies}}
    
    def _build_search_request(
        self,
        query: str,
        max_results: int,
        offset: int,
        sort_by: str,
        field_selection: str,
        filters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build Elasticsearch query for persons."""
        
        # Start with base query structure
        es_query = {
            "size": max_results,
            "from": offset
        }
        
        # Build query clauses
        must_clauses = []
        filter_clauses = []
        
        # Main query - use multi-strategy person search
        if query:
            must_clauses.append(self._build_person_query(query))
        
        # Apply filters
        if filters.get('active_only', True):
            filter_clauses.append({"term": {"IsActive": True}})
        
        if filters.get('organization'):
            # Search in organization names - ES 6.x doesn't support nested queries well
            # Use a simpler approach
            filter_clauses.append({
                "bool": {
                    "should": [
                        {"match": {"OrganizationHome.DisplayNameEng": filters['organization']}},
                        {"match": {"OrganizationHome.DisplayNameSwe": filters['organization']}},
                        {"match": {"OrganizationHome.NameEng": filters['organization']}},
                        {"match": {"OrganizationHome.NameSwe": filters['organization']}}
                    ],
                    "minimum_should_match": 1
                }
            })
        
        if filters.get('has_orcid') is not None:
            if filters['has_orcid']:
                filter_clauses.append({"exists": {"field": "IdentifierOrcid"}})
            else:
                filter_clauses.append({"bool": {"must_not": {"exists": {"field": "IdentifierOrcid"}}}})
        
        if filters.get('has_publications') is not None:
            filter_clauses.append({"term": {"HasPublications": filters['has_publications']}})
        
        # Always exclude deleted records
        filter_clauses.append({"term": {"IsDeleted": False}})
        
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
        """Build sort clause specific to persons."""
        if sort_by == "relevance":
            return ["_score", {"DisplayName.keyword": "asc"}]
        elif sort_by == "name_asc":
            return [{"DisplayName.keyword": "asc"}]
        elif sort_by == "date_desc":
            # Sort by creation date if available
            return [{"CreatedAt": "desc"}, {"DisplayName.keyword": "asc"}]
        elif sort_by == "date_asc":
            return [{"CreatedAt": "asc"}, {"DisplayName.keyword": "asc"}]
        else:
            return ["_score"]
    
    def _get_source_fields(self, field_selection: str) -> Optional[List[str]]:
        """Get source fields to retrieve based on selection level."""
        if field_selection == "standard":
            return [
                "Id", "DisplayName", "FirstName", "LastName",
                "IsActive", "HasPublications", "HasProjects",
                "IdentifierOrcid", "HasIdentifiers"
            ]
        elif field_selection == "expanded":
            return [
                "Id", "DisplayName", "FirstName", "LastName",
                "IsActive", "HasPublications", "HasProjects",
                "IdentifierOrcid", "IdentifierCid", "Identifiers",
                "OrganizationHome", "OrganizationHomeCount"
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
            
            if field_selection == "standard":
                # Minimal fields
                person = PersonStandard(
                    id=doc['Id'],
                    display_name=doc['DisplayName'],
                    first_name=doc.get('FirstName'),
                    last_name=doc.get('LastName'),
                    is_active=doc.get('IsActive', False),
                    has_publications=doc.get('HasPublications', False),
                    has_orcid=bool(doc.get('IdentifierOrcid')),
                    score=score
                )
                transformed.append(person.model_dump())
                
            elif field_selection == "expanded":
                # Include identifiers and affiliations
                # Extract ORCID
                orcid = None
                if doc.get('IdentifierOrcid'):
                    orcid = doc['IdentifierOrcid'][0] if isinstance(doc['IdentifierOrcid'], list) else doc['IdentifierOrcid']
                
                # Extract Scopus ID from Identifiers array
                scopus_id = self._extract_identifier(doc.get('Identifiers', []), 'ScopusAuthorId')
                
                # Extract organization names
                org_names = []
                if doc.get('OrganizationHome'):
                    for org in doc['OrganizationHome']:
                        if isinstance(org, dict):
                            name = org.get('DisplayNameEng') or org.get('DisplayNameSwe') or org.get('NameEng')
                            if name:
                                org_names.append(name)
                
                person = PersonExpanded(
                    id=doc['Id'],
                    display_name=doc['DisplayName'],
                    first_name=doc.get('FirstName'),
                    last_name=doc.get('LastName'),
                    is_active=doc.get('IsActive', False),
                    has_publications=doc.get('HasPublications', False),
                    has_orcid=bool(orcid),
                    score=score,
                    orcid=orcid,
                    scopus_id=scopus_id,
                    organization_names=org_names[:5],  # Limit to 5
                    organization_count=doc.get('OrganizationHomeCount', 0),
                    has_projects=doc.get('HasProjects', False)
                )
                transformed.append(person.model_dump())
                
            else:  # full
                # Return most fields but clean up maintenance fields
                full_doc = {
                    'id': doc['Id'],
                    'display_name': doc['DisplayName'],
                    'first_name': doc.get('FirstName'),
                    'last_name': doc.get('LastName'),
                    'is_active': doc.get('IsActive', False),
                    'has_publications': doc.get('HasPublications', False),
                    'has_projects': doc.get('HasProjects', False),
                    'has_orcid': bool(doc.get('IdentifierOrcid')),
                    'score': score,
                    'birth_year': doc.get('BirthYear', 0) if doc.get('BirthYear', 0) > 0 else None,
                    'identifiers': doc.get('Identifiers', []),
                    'organizations': doc.get('OrganizationHome', []),
                    'pdb_categories': doc.get('PdbCategories', []),
                }
                
                # Add all identifier arrays
                if doc.get('IdentifierOrcid'):
                    full_doc['orcid'] = doc['IdentifierOrcid'][0] if isinstance(doc['IdentifierOrcid'], list) else doc['IdentifierOrcid']
                if doc.get('IdentifierCid'):
                    full_doc['chalmers_id'] = doc['IdentifierCid']
                
                transformed.append(full_doc)
        
        return transformed
    
    def _extract_identifier(self, identifiers: List[Dict], id_type: str) -> Optional[str]:
        """Extract a specific identifier type from the identifiers array."""
        for identifier in identifiers:
            if identifier.get('Type') == id_type and identifier.get('IsActive', True):
                return identifier.get('Value')
        return None