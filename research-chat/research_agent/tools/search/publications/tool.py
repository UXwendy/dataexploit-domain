"""Publications search tool implementation."""
from typing import Dict, Any, List, Optional, Type

from ..base.elasticsearch_tool import BaseElasticsearchSearchTool
from .models import PublicationsSearchInput, PublicationStandard, PublicationExpanded, PublicationFull
from ...utils.text import truncate_text, safe_get_nested
from ..utils.organization_mapper import get_organization_mapper


class PublicationsSearchTool(BaseElasticsearchSearchTool):
    """Search tool for academic publications."""
    
    name: str = "search_publications"
    description: str = """Search for academic publications in the Chalmers research database.
    
    This is the primary tool for discovering research on any topic, finding prolific authors,
    and analyzing research trends. Searches are performed across title, abstract, and keywords
    using relevance scoring.
    
    For finding researchers by expertise: search publications on a topic first, then analyze
    the authors in results. Use faceting for automatic author frequency analysis.
    
    Input can be keywords, author names, or filter combinations.
    
    Note: Zero results may indicate overly specific search terms. Try broader concepts.
    If no results found, respond with helpful suggestions for alternative searches.
    """
    
    args_schema: Type[PublicationsSearchInput] = PublicationsSearchInput
    
    def _build_search_request(
        self,
        query: str,
        max_results: int,
        offset: int,
        sort_by: str,
        field_selection: str,
        filters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build Elasticsearch query for publications."""
        
        # Start with base query structure
        es_query = {
            "size": max_results,
            "from": offset
        }
        
        # Build query clauses
        must_clauses = []
        filter_clauses = []
        
        # Main query - search in multiple fields
        if query:
            must_clauses.append({
                "multi_match": {
                    "query": query,
                    "fields": [
                        "Title^3",
                        "Abstract^2",
                        "Keywords.Value",
                        "Persons.PersonData.DisplayName",
                        "Source.SourceSerial.Title"
                    ],
                    "type": "best_fields",
                    "operator": "and"
                }
            })
        
        # Author filter
        if filters.get('authors'):
            for author in filters['authors']:
                filter_clauses.append({
                    "bool": {
                        "should": [
                            {"match_phrase": {"Persons.PersonData.DisplayName": author}},
                            {"match_phrase": {"Persons.PersonData.DisplayName.keyword": author}}
                        ],
                        "minimum_should_match": 1
                    }
                })
        
        # Year filters
        if filters.get('year_from') is not None:
            filter_clauses.append({
                "range": {"Year": {"gte": filters['year_from']}}
            })
        
        if filters.get('year_to') is not None:
            filter_clauses.append({
                "range": {"Year": {"lte": filters['year_to']}}
            })
        
        # Publication type filter
        if filters.get('publication_types'):
            type_clauses = []
            for pub_type in filters['publication_types']:
                type_clauses.extend([
                    {"match": {"PublicationType.NameEng": pub_type}},
                    {"match": {"PublicationType.NameSwe": pub_type}}
                ])
            
            filter_clauses.append({
                "bool": {
                    "should": type_clauses,
                    "minimum_should_match": 1
                }
            })
        
        # Keywords filter
        if filters.get('keywords'):
            for keyword in filters['keywords']:
                filter_clauses.append({
                    "match": {"Keywords.Value": keyword}
                })
        
        # Source filter
        if filters.get('source'):
            filter_clauses.append({
                "match": {"Source.SourceSerial.Title": filters['source']}
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
                    {"match": {"Persons.Organizations.OrganizationData.DisplayNameEng": term}},
                    {"match": {"Persons.Organizations.OrganizationData.DisplayNameSwe": term}},
                    {"match": {"Persons.Organizations.OrganizationData.NameEng": term}},
                    {"match": {"Persons.Organizations.OrganizationData.NameSwe": term}}
                ])
            
            filter_clauses.append({
                "bool": {
                    "should": should_clauses,
                    "minimum_should_match": 1
                }
            })
        
        # Always exclude deleted and draft documents
        filter_clauses.extend([
            {"term": {"IsDeleted": False}},
            {"term": {"IsDraft": False}}
        ])
        
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
        """Build sort clause specific to publications."""
        if sort_by == "relevance":
            return ["_score", {"Year": {"order": "desc", "missing": "_last"}}]
        elif sort_by == "date_desc":
            return [{"Year": {"order": "desc", "missing": "_last"}}, {"_score": {"order": "desc"}}]
        elif sort_by == "date_asc":
            return [{"Year": {"order": "asc", "missing": "_last"}}, {"_score": {"order": "desc"}}]
        elif sort_by == "name_asc":
            return [{"Title": {"order": "asc"}}]
        else:
            return ["_score"]
    
    def _build_facets(self, facet_types: List[str], size: int) -> Dict[str, Any]:
        """Build aggregations for requested facets."""
        aggs = {}
        
        for facet in facet_types:
            if facet == "authors":
                aggs["top_authors"] = {
                    "terms": {
                        "field": "Persons.PersonData.DisplayName.keyword",
                        "size": size,
                        "order": {"_count": "desc"}
                    }
                }
            elif facet == "organizations":
                aggs["top_organizations"] = {
                    "terms": {
                        "field": "Persons.Organizations.OrganizationData.DisplayNameEng.keyword",
                        "size": size,
                        "order": {"_count": "desc"}
                    }
                }
            elif facet == "years":
                aggs["publication_years"] = {
                    "terms": {
                        "field": "Year",
                        "size": size,
                        "order": {"_key": "desc"}
                    }
                }
            elif facet == "types":
                aggs["publication_types"] = {
                    "terms": {
                        "field": "PublicationType.NameEng.keyword",
                        "size": size,
                        "order": {"_count": "desc"}
                    }
                }
            elif facet == "keywords":
                aggs["top_keywords"] = {
                    "terms": {
                        "field": "Keywords.Value.keyword",
                        "size": size,
                        "order": {"_count": "desc"}
                    }
                }
        
        return aggs
    
    def _get_source_fields(self, field_selection: str) -> Optional[List[str]]:
        """Get source fields to retrieve based on selection level."""
        if field_selection == "standard":
            return [
                "Id", "Title", "Year", "PublicationType",
                "Source", "Persons", "HasPersons"
            ]
        elif field_selection == "expanded":
            return [
                "Id", "Title", "Abstract", "Year", "PublicationType",
                "Source", "Persons", "Keywords", "Language",
                "IdentifierDoi", "IdentifierScopusId", "DataObjects",
                "HasPersons", "HasOrganizations"
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
            
            # Extract common fields
            pub_type = safe_get_nested(doc, 'PublicationType.NameEng')
            source_title = safe_get_nested(doc, 'Source.SourceSerial.Title')
            
            if field_selection == "standard":
                # Minimal fields with simplified authors
                author_names = self._extract_author_names(doc.get('Persons', []))
                
                pub = PublicationStandard(
                    id=doc['Id'],
                    title=doc.get('Title', 'Untitled'),
                    year=doc.get('Year'),
                    publication_type=pub_type,
                    source_title=source_title,
                    author_names=author_names[:10],  # Limit to 10
                    author_count=len(doc.get('Persons', [])),
                    score=score
                )
                transformed.append(pub.model_dump())
                
            elif field_selection == "expanded":
                # Include abstract and structured authors
                abstract = truncate_text(doc.get('Abstract', ''), 500)
                keywords = self._extract_keywords(doc.get('Keywords', []))
                doi = self._extract_doi(doc)
                scopus_id = self._extract_scopus_id(doc)
                authors = self._extract_author_details(doc.get('Persons', []))
                is_open_access = self._check_open_access(doc.get('DataObjects', []))
                language = safe_get_nested(doc, 'Language.NameEng')
                
                pub = PublicationExpanded(
                    id=doc['Id'],
                    title=doc.get('Title', 'Untitled'),
                    year=doc.get('Year'),
                    publication_type=pub_type,
                    source_title=source_title,
                    author_names=self._extract_author_names(doc.get('Persons', [])),
                    author_count=len(doc.get('Persons', [])),
                    score=score,
                    abstract=abstract,
                    keywords=keywords[:10],  # Limit keywords
                    doi=doi,
                    scopus_id=scopus_id,
                    authors=authors[:20],  # Limit to 20 authors
                    source=doc.get('Source'),
                    is_open_access=is_open_access,
                    language=language
                )
                transformed.append(pub.model_dump())
                
            else:  # full
                # Return comprehensive data
                full_doc = {
                    'id': doc['Id'],
                    'title': doc.get('Title', 'Untitled'),
                    'year': doc.get('Year'),
                    'publication_type': pub_type,
                    'source_title': source_title,
                    'author_names': self._extract_author_names(doc.get('Persons', [])),
                    'author_count': len(doc.get('Persons', [])),
                    'score': score,
                    'abstract_full': doc.get('Abstract'),
                    'keywords': self._extract_keywords(doc.get('Keywords', [])),
                    'all_identifiers': {
                        'doi': doc.get('IdentifierDoi', []),
                        'scopus': doc.get('IdentifierScopusId', []),
                        'pubmed': doc.get('IdentifierPubmedId', []),
                        'isbn': doc.get('IdentifierIsbn', []),
                        'cpl_pubid': doc.get('IdentifierCplPubid', [])
                    },
                    'persons': self._extract_limited_person_data(doc.get('Persons', [])),
                    'organizations': doc.get('Organizations', []),
                    'categories': doc.get('Categories', []),
                    'data_objects': doc.get('DataObjects', []),
                    'details_url_eng': doc.get('DetailsUrlEng'),
                    'details_url_swe': doc.get('DetailsUrlSwe'),
                    'source': doc.get('Source'),
                    'language': safe_get_nested(doc, 'Language.NameEng')
                }
                transformed.append(full_doc)
        
        return transformed
    
    def _extract_author_names(self, persons: List[Dict]) -> List[str]:
        """Extract simple author name list."""
        names = []
        for person in persons:
            name = safe_get_nested(person, 'PersonData.DisplayName')
            if name:
                names.append(name)
        return names
    
    def _extract_author_details(self, persons: List[Dict]) -> List[Dict[str, Any]]:
        """Extract structured author information for expanded view."""
        authors = []
        for person in persons[:20]:  # Limit processing
            person_data = person.get('PersonData', {})
            
            # Get first affiliation
            affiliation = None
            if person.get('Organizations'):
                org = person['Organizations'][0] if person['Organizations'] else {}
                affiliation = safe_get_nested(org, 'OrganizationData.DisplayNameEng')
            
            author = {
                'name': person_data.get('DisplayName', ''),
                'id': person_data.get('Id'),
                'order': person.get('Order'),
                'role': safe_get_nested(person, 'Role.NameEng'),
                'affiliation': affiliation,
                'orcid': person_data.get('IdentifierOrcid', [None])[0] if person_data.get('IdentifierOrcid') else None
            }
            authors.append(author)
        
        return authors
    
    def _extract_limited_person_data(self, persons: List[Dict]) -> List[Dict[str, Any]]:
        """Extract limited person data for full view (avoid massive nested data)."""
        limited = []
        for person in persons[:50]:  # Hard limit
            person_data = person.get('PersonData', {})
            limited.append({
                'id': person_data.get('Id'),
                'display_name': person_data.get('DisplayName'),
                'first_name': person_data.get('FirstName'),
                'last_name': person_data.get('LastName'),
                'order': person.get('Order'),
                'role': safe_get_nested(person, 'Role.NameEng'),
                'first_organization': safe_get_nested(person, 'Organizations.0.OrganizationData.DisplayNameEng')
            })
        return limited
    
    def _extract_keywords(self, keywords: List[Any]) -> List[str]:
        """Extract keyword values."""
        result = []
        for kw in keywords:
            if isinstance(kw, dict) and 'Value' in kw:
                result.append(kw['Value'])
            elif isinstance(kw, str):
                result.append(kw)
        return result
    
    def _extract_doi(self, doc: Dict) -> Optional[str]:
        """Extract DOI if available."""
        doi_list = doc.get('IdentifierDoi', [])
        return doi_list[0] if doi_list else None
    
    def _extract_scopus_id(self, doc: Dict) -> Optional[str]:
        """Extract Scopus ID if available."""
        scopus_list = doc.get('IdentifierScopusId', [])
        return scopus_list[0] if scopus_list else None
    
    def _check_open_access(self, data_objects: List[Dict]) -> bool:
        """Check if any data object indicates open access."""
        for obj in data_objects:
            if obj.get('IsOpenAccess'):
                return True
        return False