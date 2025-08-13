"""Projects search tool implementation."""
from typing import Dict, Any, List, Optional, Type
from datetime import datetime

from ..base.elasticsearch_tool import BaseElasticsearchSearchTool
from .models import ProjectsSearchInput, ProjectStandard, ProjectExpanded, ProjectFull
from ...utils.text import truncate_text
from ..utils.organization_mapper import get_organization_mapper


class ProjectsSearchTool(BaseElasticsearchSearchTool):
    """Search tool for research projects."""
    
    name: str = "search_projects"
    description: str = """Search for research projects and grants in the Chalmers database.
    
    Useful for finding funded research initiatives, industry collaborations, and analyzing
    research funding patterns. Complements publication searches by showing ongoing/future work.
    
    Searches are performed across project titles and descriptions using relevance scoring.
    Can filter by funder, status, funding amount, and date ranges. Use faceting for funding analysis.
    
    Input can be keywords, funder names, or filter combinations.
    
    Note: Zero results may indicate overly specific search terms. Try broader concepts.
    If no results found, respond with helpful suggestions for alternative searches.
    """
    
    args_schema: Type[ProjectsSearchInput] = ProjectsSearchInput
    
    def _build_search_request(
        self,
        query: str,
        max_results: int,
        offset: int,
        sort_by: str,
        field_selection: str,
        filters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build Elasticsearch query for projects."""
        
        # Start with base query structure
        es_query = {
            "size": max_results,
            "from": offset
        }
        
        # Build query clauses
        must_clauses = []
        filter_clauses = []
        
        # Main query - search in title and description fields
        if query:
            must_clauses.append({
                "multi_match": {
                    "query": query,
                    "fields": [
                        "ProjectTitleEng^3",
                        "ProjectTitleSwe^2",
                        "ProjectDescriptionEng",
                        "ProjectDescriptionSwe",
                        "Keywords"
                    ],
                    "type": "best_fields"
                }
            })
        
        # Date filters
        current_date = datetime.now()
        
        if filters.get('start_year'):
            filter_clauses.append({
                "range": {
                    "StartDate": {
                        "gte": f"{filters['start_year']}-01-01T00:00:00"
                    }
                }
            })
        
        if filters.get('end_year'):
            filter_clauses.append({
                "range": {
                    "EndDate": {
                        "lte": f"{filters['end_year']}-12-31T23:59:59"
                    }
                }
            })
        
        # Status filter
        if filters.get('status'):
            if filters['status'] == 'active':
                # Active: started and not ended yet
                filter_clauses.extend([
                    {"range": {"StartDate": {"lte": current_date.isoformat()}}},
                    {"range": {"EndDate": {"gte": current_date.isoformat()}}}
                ])
            elif filters['status'] == 'completed':
                # Completed: ended before today
                filter_clauses.append({
                    "range": {"EndDate": {"lt": current_date.isoformat()}}
                })
            elif filters['status'] == 'upcoming':
                # Upcoming: starts after today
                filter_clauses.append({
                    "range": {"StartDate": {"gt": current_date.isoformat()}}
                })
        
        # Funding filter
        if filters.get('min_funding') is not None:
            filter_clauses.append({
                "range": {
                    "Contracts.ContractAmount": {
                        "gte": filters['min_funding']
                    }
                }
            })
        
        # Funder filter
        if filters.get('funder'):
            filter_clauses.append({
                "bool": {
                    "should": [
                        {"match": {"Contracts.ContractOrganization.DisplayNameEng": filters['funder']}},
                        {"match": {"Contracts.ContractOrganization.DisplayNameSwe": filters['funder']}},
                        {"match": {"Contracts.ContractOrganization.NameEng": filters['funder']}},
                        {"match": {"Contracts.ContractOrganization.NameSwe": filters['funder']}}
                    ],
                    "minimum_should_match": 1
                }
            })
        
        # Organization filter
        if filters.get('organization'):
            # Get all search terms for the organization (including aliases and hierarchy)
            mapper = get_organization_mapper()
            org_terms = mapper.get_search_terms(filters['organization'], include_hierarchy=True)
            
            # Build should clauses for all terms
            should_clauses = []
            for term in org_terms:
                should_clauses.extend([
                    {"match": {"Organizations.DisplayNameEng": term}},
                    {"match": {"Organizations.DisplayNameSwe": term}},
                    {"match": {"Organizations.NameEng": term}},
                    {"match": {"Organizations.NameSwe": term}}
                ])
            
            filter_clauses.append({
                "bool": {
                    "should": should_clauses,
                    "minimum_should_match": 1
                }
            })
        
        # PI name filter
        if filters.get('pi_name'):
            filter_clauses.append({
                "bool": {
                    "must": [
                        {"match": {"Persons.PersonData.DisplayName": filters['pi_name']}},
                        {
                            "bool": {
                                "should": [
                                    {"term": {"Persons.PersonRoleID": 1}},
                                    {"match": {"Persons.PersonRole.NameEng": "Principal investigator"}},
                                    {"match": {"Persons.PersonRole.NameEng": "Project Manager"}}
                                ],
                                "minimum_should_match": 1
                            }
                        }
                    ]
                }
            })
        
        # Always filter by publish status (only published projects)
        filter_clauses.append({"term": {"PublishStatus": 3}})
        
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
        
        # Add facets/aggregations if requested
        if filters.get('include_facets'):
            es_query["aggs"] = self._build_facets(
                filters['include_facets'], 
                filters.get('facet_size', 20)
            )
        
        return es_query
    
    def _build_sort_clause(self, sort_by: str) -> List[Dict[str, Any]]:
        """Build sort clause specific to projects."""
        if sort_by == "relevance":
            return ["_score", {"StartDate": "desc"}]
        elif sort_by == "date_desc":
            return [{"StartDate": "desc"}]
        elif sort_by == "date_asc":
            return [{"StartDate": "asc"}]
        elif sort_by == "name_asc":
            return [{"ProjectTitleEng": "asc"}]
        else:
            return ["_score"]
    
    def _build_facets(self, facet_types: List[str], size: int) -> Dict[str, Any]:
        """Build aggregations for requested facets."""
        aggs = {}
        current_date = datetime.now().isoformat()
        
        for facet in facet_types:
            if facet == "funders":
                aggs["top_funders"] = {
                    "terms": {
                        "field": "Contracts.ContractOrganization.DisplayNameEng.keyword",
                        "size": size,
                        "order": {"_count": "desc"}
                    }
                }
            elif facet == "organizations":
                aggs["top_organizations"] = {
                    "terms": {
                        "field": "Organizations.DisplayNameEng.keyword",
                        "size": size,
                        "order": {"_count": "desc"}
                    }
                }
            elif facet == "years":
                aggs["start_years"] = {
                    "date_histogram": {
                        "field": "StartDate",
                        "calendar_interval": "year",
                        "format": "yyyy",
                        "order": {"_key": "desc"}
                    }
                }
            elif facet == "status":
                # Status is computed, so we need to use ranges
                aggs["project_status"] = {
                    "filters": {
                        "filters": {
                            "active": {
                                "bool": {
                                    "must": [
                                        {"range": {"StartDate": {"lte": current_date}}},
                                        {"range": {"EndDate": {"gte": current_date}}}
                                    ]
                                }
                            },
                            "completed": {
                                "range": {"EndDate": {"lt": current_date}}
                            },
                            "upcoming": {
                                "range": {"StartDate": {"gt": current_date}}
                            }
                        }
                    }
                }
            elif facet == "pis":
                # PIs are those with specific roles
                aggs["top_pis"] = {
                    "nested": {
                        "path": "Persons"
                    },
                    "aggs": {
                        "pi_filter": {
                            "filter": {
                                "bool": {
                                    "should": [
                                        {"term": {"Persons.PersonRoleID": 1}},
                                        {"match": {"Persons.PersonRole.NameEng": "Principal investigator"}}
                                    ]
                                }
                            },
                            "aggs": {
                                "names": {
                                    "terms": {
                                        "field": "Persons.PersonData.DisplayName.keyword",
                                        "size": size,
                                        "order": {"_count": "desc"}
                                    }
                                }
                            }
                        }
                    }
                }
        
        return aggs
    
    def _get_source_fields(self, field_selection: str) -> Optional[List[str]]:
        """Get source fields to retrieve based on selection level."""
        if field_selection == "standard":
            return [
                "ID", "ProjectTitleEng", "ProjectTitleSwe",
                "StartDate", "EndDate",
                "Contracts", "Persons"
            ]
        elif field_selection == "expanded":
            return [
                "ID", "ProjectTitleEng", "ProjectTitleSwe",
                "ProjectDescriptionEng", "ProjectDescriptionSwe",
                "StartDate", "EndDate",
                "Contracts", "Persons", "Organizations",
                "Keywords"
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
        current_date = datetime.now()
        
        for hit in raw_results['hits']['hits']:
            doc = hit.get('_source')
            if not doc:
                continue
            score = hit.get('_score')
            
            # Compute common fields
            status = self._compute_status(doc.get('StartDate'), doc.get('EndDate'), current_date)
            total_funding, currency = self._extract_funding_info(doc.get('Contracts', []))
            pi_name = self._extract_pi_name(doc.get('Persons', []))
            
            if field_selection == "standard":
                # Minimal fields
                project = ProjectStandard(
                    id=doc['ID'],
                    title=doc.get('ProjectTitleEng') or doc.get('ProjectTitleSwe', 'Untitled'),
                    start_date=doc.get('StartDate'),
                    end_date=doc.get('EndDate'),
                    status=status,
                    total_funding=total_funding,
                    currency=currency,
                    pi_name=pi_name,
                    score=score
                )
                transformed.append(project.model_dump())
                
            elif field_selection == "expanded":
                # Include description and participants
                description = doc.get('ProjectDescriptionEng') or doc.get('ProjectDescriptionSwe', '')
                description = truncate_text(description, 500)
                
                funder_names = self._extract_funder_names(doc.get('Contracts', []))
                participant_names = self._extract_participant_names(doc.get('Persons', []))
                
                project = ProjectExpanded(
                    id=doc['ID'],
                    title=doc.get('ProjectTitleEng') or doc.get('ProjectTitleSwe', 'Untitled'),
                    start_date=doc.get('StartDate'),
                    end_date=doc.get('EndDate'),
                    status=status,
                    total_funding=total_funding,
                    currency=currency,
                    pi_name=pi_name,
                    score=score,
                    description=description,
                    funder_names=funder_names[:5],  # Limit to 5
                    participant_count=len(doc.get('Persons', [])),
                    participant_names=participant_names[:10],  # Limit to 10
                    organization_count=len(doc.get('Organizations', []))
                )
                transformed.append(project.model_dump())
                
            else:  # full
                # Return most fields
                full_doc = {
                    'id': doc['ID'],
                    'title': doc.get('ProjectTitleEng') or doc.get('ProjectTitleSwe', 'Untitled'),
                    'title_swe': doc.get('ProjectTitleSwe'),
                    'start_date': doc.get('StartDate'),
                    'end_date': doc.get('EndDate'),
                    'status': status,
                    'total_funding': total_funding,
                    'currency': currency,
                    'pi_name': pi_name,
                    'score': score,
                    'description_full': doc.get('ProjectDescriptionEng') or doc.get('ProjectDescriptionSwe'),
                    'description_swe': doc.get('ProjectDescriptionSwe'),
                    'contracts': doc.get('Contracts', []),
                    'persons': doc.get('Persons', []),
                    'organizations': doc.get('Organizations', []),
                    'keywords': doc.get('Keywords', []),
                    'categories': doc.get('Categories', [])
                }
                transformed.append(full_doc)
        
        return transformed
    
    def _compute_status(self, start_date: Optional[str], end_date: Optional[str], current_date: datetime) -> str:
        """Compute project status based on dates."""
        if not start_date:
            return "unknown"
        
        try:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            
            if start > current_date:
                return "upcoming"
            
            if end_date:
                end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                if end < current_date:
                    return "completed"
                else:
                    return "active"
            else:
                return "active"  # No end date means ongoing
                
        except:
            return "unknown"
    
    def _extract_funding_info(self, contracts: List[Dict]) -> tuple[Optional[float], Optional[str]]:
        """Extract total funding and currency from contracts."""
        if not contracts:
            return None, None
        
        total = 0
        currency = None
        
        for contract in contracts:
            if 'ContractAmount' in contract:
                total += contract['ContractAmount']
                if not currency and 'ContractCurrencyCode' in contract:
                    currency = contract['ContractCurrencyCode']
        
        return total if total > 0 else None, currency
    
    def _extract_pi_name(self, persons: List[Dict]) -> Optional[str]:
        """Extract principal investigator name."""
        for person in persons:
            # Look for PI role (role ID might vary)
            if person.get('PersonRoleID') == 1 or person.get('PersonRole', {}).get('NameEng') == 'Principal investigator':
                person_data = person.get('PersonData', {})
                return person_data.get('DisplayName') or f"{person_data.get('FirstName', '')} {person_data.get('LastName', '')}".strip()
        
        # If no PI found, return first person
        if persons:
            person_data = persons[0].get('PersonData', {})
            return person_data.get('DisplayName') or f"{person_data.get('FirstName', '')} {person_data.get('LastName', '')}".strip()
        
        return None
    
    def _extract_funder_names(self, contracts: List[Dict]) -> List[str]:
        """Extract unique funder names."""
        funders = set()
        
        for contract in contracts:
            org = contract.get('ContractOrganization', {})
            name = org.get('DisplayNameEng') or org.get('DisplayNameSwe') or org.get('NameEng')
            if name:
                funders.add(name)
        
        return sorted(list(funders))
    
    def _extract_participant_names(self, persons: List[Dict]) -> List[str]:
        """Extract participant names."""
        names = []
        
        for person in persons:
            person_data = person.get('PersonData', {})
            name = person_data.get('DisplayName') or f"{person_data.get('FirstName', '')} {person_data.get('LastName', '')}".strip()
            if name:
                names.append(name)
        
        return names