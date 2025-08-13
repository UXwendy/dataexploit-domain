"""Elasticsearch query builder with smart field selection."""
from typing import Dict, List, Any, Optional
from ..models.common import (
    SearchFilters, SortBy, SearchField, FieldSelection, FIELD_PRESETS
)
from ..models.search import SearchInput


class ElasticsearchQueryBuilder:
    """Build Elasticsearch queries with proper field handling."""
    
    @staticmethod
    def build_search_query(search_input: SearchInput) -> Dict[str, Any]:
        """
        Build complete Elasticsearch query from search input.
        
        Returns a query dict ready for es_client.search()
        """
        # Start with base structure
        query_body = {
            "size": search_input.max_results,
            "from": search_input.offset,
            "track_total_hits": True,
            "_source": ElasticsearchQueryBuilder._get_source_fields(search_input.field_selection)
        }
        
        # Build the main query
        must_clauses = []
        
        # Add main search query if provided
        if search_input.query:
            search_clause = ElasticsearchQueryBuilder._build_search_clause(
                search_input.query, 
                search_input.fields_to_search
            )
            must_clauses.append(search_clause)
        
        # Add filters
        filter_clauses = []
        if search_input.filters:
            filter_clauses = ElasticsearchQueryBuilder._build_filter_clauses(search_input.filters)
        
        # Combine query and filters
        if must_clauses or filter_clauses:
            bool_query = {}
            if must_clauses:
                bool_query["must"] = must_clauses
            if filter_clauses:
                bool_query["filter"] = filter_clauses
            query_body["query"] = {"bool": bool_query}
        else:
            # No query or filters - match all
            query_body["query"] = {"match_all": {}}
        
        # Add sorting
        query_body["sort"] = ElasticsearchQueryBuilder._build_sort(search_input.sort_by)
        
        return query_body
    
    @staticmethod
    def _get_source_fields(field_selection: FieldSelection) -> List[str]:
        """Get the list of fields to retrieve based on selection strategy."""
        # Get base fields from preset
        fields = FIELD_PRESETS.get(field_selection, FIELD_PRESETS[FieldSelection.STANDARD]).copy()
        
        # Special handling for nested fields
        # We always need to get full Persons/Organizations if requested,
        # but we'll extract only what we need in the response parser
        return fields
    
    @staticmethod
    def _build_search_clause(query: str, fields: List[SearchField]) -> Dict[str, Any]:
        """Build the search clause based on fields to search."""
        # Convert enum values to strings if needed
        field_values = [f.value if hasattr(f, 'value') else f for f in fields]
        
        if SearchField.ALL.value in field_values or "all" in field_values:
            # Search across all relevant fields with boosting
            return {
                "multi_match": {
                    "query": query,
                    "fields": [
                        "Title^3",           # Title gets highest boost
                        "Abstract^2",        # Abstract gets medium boost
                        "Persons.PersonData.DisplayName^2",  # Authors get medium boost
                        "Keywords^1.5",      # Keywords slightly boosted
                        "Source"            # Journal name normal weight
                    ],
                    "type": "best_fields",
                    "fuzziness": "AUTO"
                }
            }
        else:
            # Map field names to Elasticsearch fields
            field_mapping = {
                SearchField.TITLE.value: "Title",
                SearchField.ABSTRACT.value: "Abstract", 
                SearchField.AUTHORS.value: "Persons.PersonData.DisplayName",
                SearchField.KEYWORDS.value: "Keywords",
                SearchField.SOURCE.value: "Source"
            }
            
            es_fields = []
            for f in field_values:
                mapped = field_mapping.get(f)
                if mapped:
                    es_fields.append(mapped)
            
            if not es_fields:
                # Fallback to title if no valid fields
                es_fields = ["Title"]
            
            if len(es_fields) == 1:
                # Single field search
                return {
                    "match": {
                        es_fields[0]: {
                            "query": query,
                            "fuzziness": "AUTO"
                        }
                    }
                }
            else:
                # Multi-field search
                return {
                    "multi_match": {
                        "query": query,
                        "fields": es_fields,
                        "type": "best_fields",
                        "fuzziness": "AUTO"
                    }
                }
    
    @staticmethod
    def _build_filter_clauses(filters: SearchFilters) -> List[Dict[str, Any]]:
        """Build filter clauses from filters object."""
        clauses = []
        
        # Author filter - try without nested first (ES 6.x compatibility)
        if filters.authors:
            for author in filters.authors:
                # Simplified query for ES 6.x - no nested query
                clauses.append({
                    "bool": {
                        "should": [
                            {"match_phrase": {"Persons.PersonData.DisplayName": author}},
                            {"match_phrase": {"Persons.PersonData.DisplayName.keyword": author}}
                        ],
                        "minimum_should_match": 1
                    }
                })
        
        # Year range filter  
        if filters.years:
            year_filter = {"range": {"Year": {}}}
            if filters.years.from_year:
                year_filter["range"]["Year"]["gte"] = filters.years.from_year
            if filters.years.to_year:
                year_filter["range"]["Year"]["lte"] = filters.years.to_year
            clauses.append(year_filter)
        
        # Publication type filter
        if filters.publication_types:
            clauses.append({
                "terms": {
                    "PublicationType.DisplayNameEng.keyword": filters.publication_types
                }
            })
        
        # Source filter
        if filters.sources:
            clauses.append({
                "terms": {
                    "Source.keyword": filters.sources
                }
            })
        
        # Keywords filter
        if filters.keywords:
            keyword_clauses = []
            for keyword in filters.keywords:
                keyword_clauses.append({
                    "match": {
                        "Keywords": keyword
                    }
                })
            # All keywords should match
            clauses.append({
                "bool": {
                    "must": keyword_clauses
                }
            })
        
        # Language filter
        if filters.language:
            clauses.append({
                "term": {
                    "Language": filters.language
                }
            })
        
        return clauses
    
    @staticmethod
    def _build_sort(sort_by: SortBy) -> List[Dict[str, Any]]:
        """Build sort clause based on sort option."""
        # Handle enum value
        sort_value = sort_by.value if hasattr(sort_by, 'value') else sort_by
        
        if sort_value == SortBy.RELEVANCE.value:
            return [{"_score": {"order": "desc"}}]
        elif sort_value == SortBy.YEAR_DESC.value:
            return [
                {"Year": {"order": "desc", "missing": "_last"}},
                {"_score": {"order": "desc"}}
            ]
        elif sort_value == SortBy.YEAR_ASC.value:
            return [
                {"Year": {"order": "asc", "missing": "_last"}},
                {"_score": {"order": "desc"}}
            ]
        elif sort_value == SortBy.NAME_ASC.value:
            return [{"Title": {"order": "asc"}}]
        elif sort_value == SortBy.CITATIONS_DESC.value:
            return [
                {"Metrics.CitationCount": {"order": "desc", "missing": "_last"}},
                {"_score": {"order": "desc"}}
            ]
        else:
            # Default to relevance
            return [{"_score": {"order": "desc"}}]
    
    @staticmethod
    def build_document_query(document_id: str, field_selection: FieldSelection = FieldSelection.FULL_AND_SLOW) -> Dict[str, Any]:
        """Build query to get a single document by ID."""
        return {
            "query": {
                "term": {
                    "_id": document_id
                }
            },
            "size": 1,
            "_source": ElasticsearchQueryBuilder._get_source_fields(field_selection)
        }