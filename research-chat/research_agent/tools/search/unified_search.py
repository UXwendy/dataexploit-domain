"""Unified search tool for research publications."""
import json
from typing import Dict, List, Any, Optional, Type
from datetime import datetime

from langchain.tools import BaseTool
from langchain.callbacks.manager import CallbackManagerForToolRun
from elasticsearch import Elasticsearch
from pydantic import BaseModel, Field

from ..search.models.tool_inputs import UnifiedSearchInput
from ..search.models.search import (
    SearchInput, SearchResult, SearchResults, Author, PublicationType
)
from ..search.models.common import PaginationInfo
from ..search.query_builders.elasticsearch import ElasticsearchQueryBuilder
from ..utils.text import (
    truncate_text, extract_author_info, extract_source_name, 
    extract_publication_type, safe_get_nested
)
from ..config.settings import settings


class UnifiedSearchTool(BaseTool):
    """
    Unified search tool for research publications.
    
    This tool combines keyword search, author search, filtering, and sorting
    into a single flexible interface. It returns results with truncated abstracts
    and minimal author information to keep responses manageable.
    """
    
    name: str = "unified_search"
    description: str = (
        "Search tool for CHALMERS UNIVERSITY RESEARCH DATABASE ONLY. "
        "IMPORTANT: This database contains ONLY publications where at least one author is affiliated with Chalmers. "
        "It does NOT contain all global academic publications. "
        "\n"
        "CAPABILITIES:\n"
        "- Find papers by keywords, authors, years, or publication types\n"
        "- Return matching papers with their metadata\n"
        "- Sort by relevance, year, or title\n"
        "\n"
        "LIMITATIONS - This tool CANNOT:\n"
        "- Count total publications per author (no aggregation)\n"
        "- Rank authors by publication count\n"
        "- Find 'top' or 'most published' researchers\n"
        "- Compare publication counts between entities\n"
        "\n"
        "For 'most published' queries, you can only sample some authors from search results. "
        "Acknowledge this limitation in your response.\n"
        "\n"
        "EXAMPLES:\n"
        "- Good: 'Find papers by John Doe' → search with author filter\n"
        "- Good: 'Recent AI papers' → search with query and year filter\n"  
        "- Limited: 'Top 10 ML researchers' → can only show active researchers from search results"
    )
    args_schema: Type[BaseModel] = UnifiedSearchInput
    handle_tool_error: bool = True
    
    # Elasticsearch client (injected at initialization)
    es_client: Any = Field(exclude=True)
    index_name: str = Field(exclude=True)
    
    def __init__(self, es_client: Elasticsearch, index_name: Optional[str] = None):
        """Initialize the tool with Elasticsearch client."""
        if index_name is None:
            index_name = settings.ES_INDEX
        super().__init__(es_client=es_client, index_name=index_name)
    
    def _run(
        self, 
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        sort_by: str = "relevance",
        fields_to_search: List[str] = None,
        max_results: int = 10,
        offset: int = 0,
        field_selection: str = "standard",
        run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """
        Execute the search and return results as JSON string.
        
        This method is called by LangChain when the tool is invoked.
        """
        try:
            # Create SearchInput from parameters
            search_input = SearchInput(
                query=query,
                filters=filters,
                sort_by=sort_by,
                fields_to_search=fields_to_search or ["all"],
                max_results=max_results,
                offset=offset,
                field_selection=field_selection
            )
            
            # Build Elasticsearch query
            es_query = ElasticsearchQueryBuilder.build_search_query(search_input)
            
            # Execute search
            start_time = datetime.now()
            # Use ES 6.x compatible API
            response = self.es_client.search(
                index=self.index_name,
                body=es_query
            )
            search_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            # Parse results
            search_results = self._parse_results(
                response, 
                search_input, 
                search_time_ms
            )
            
            # Check if no results found and provide helpful suggestions
            if not search_results.results and search_results.pagination.total == 0:
                suggestions = self._generate_search_suggestions(search_input)
                
                # Add specific guidance for Nature/high-impact journal searches
                journal_guidance = ""
                if search_input.filters and search_input.filters.sources:
                    journal_names = search_input.filters.sources
                    if any('nature' in j.lower() for j in journal_names):
                        journal_guidance = (
                            "\n\nNOTE: 'Nature' publications are rare at Chalmers. "
                            "Try: 1) Remove source filter to find ML papers in ANY journal, "
                            "2) Search for 'Nature Communications' or 'Nature Machine Intelligence', "
                            "3) Use get_database_info(info_type='sources') to see actual journal names."
                        )
                
                # Create a helpful fallback search suggestion
                fallback_suggestion = {
                    "try_this_search": {
                        "query": query,
                        "filters": {},  # Remove all filters
                        "sort_by": "year_desc",
                        "max_results": 10
                    },
                    "explanation": "Search without filters to see what's actually available"
                }
                
                error_message = (
                    f"No results found for query '{query}'. "
                    f"Suggestions: {', '.join(suggestions)}. "
                    "Try modifying your search parameters."
                    f"{journal_guidance}"
                    f"\n\nRECOMMENDED NEXT STEP: {json.dumps(fallback_suggestion, indent=2)}"
                )
                raise ValueError(error_message)
            
            # Return as JSON for agent compatibility
            return json.dumps(search_results.model_dump(), indent=2)
            
        except Exception as e:
            # Return error as JSON with expected structure
            # Convert filters to dict if needed
            filters_dict = {}
            if filters:
                if hasattr(filters, 'model_dump'):
                    filters_dict = filters.model_dump(exclude_none=True)
                else:
                    filters_dict = filters
                    
            error_response = SearchResults(
                results=[],
                pagination=PaginationInfo(
                    offset=offset,
                    limit=max_results,
                    total=0,
                    has_more=False,
                    next_offset=None
                ),
                query=query,
                filters_applied=filters_dict,
                sort_by=sort_by,
                search_time_ms=0,
                field_selection=field_selection
            )
            
            # Add error info to the response
            response_dict = error_response.model_dump()
            response_dict["error"] = str(e)
            response_dict["error_type"] = type(e).__name__
            
            return json.dumps(response_dict, indent=2)
    
    def _parse_results(
        self, 
        es_response: Dict[str, Any], 
        search_input: SearchInput,
        search_time_ms: int
    ) -> SearchResults:
        """Parse Elasticsearch response into SearchResults model."""
        hits = es_response.get('hits', {})
        total_hits = hits.get('total', 0)
        
        # Handle both ES 6.x and 7.x total formats
        if isinstance(total_hits, dict):
            total_hits = total_hits.get('value', 0)
        
        # Parse individual results
        results = []
        for hit in hits.get('hits', []):
            result = self._parse_single_result(hit)
            if result:
                results.append(result)
        
        # Create pagination info
        pagination = PaginationInfo(
            offset=search_input.offset,
            limit=search_input.max_results,
            total=total_hits,
            has_more=(search_input.offset + search_input.max_results) < total_hits,
            next_offset=(
                search_input.offset + search_input.max_results 
                if (search_input.offset + search_input.max_results) < total_hits 
                else None
            )
        )
        
        # Prepare filters applied summary - ensure it's a dict
        filters_applied = {}
        if search_input.filters:
            filters_applied = search_input.filters.model_dump(exclude_none=True)
        
        return SearchResults(
            results=results,
            pagination=pagination,
            query=search_input.query,
            filters_applied=filters_applied,
            sort_by=search_input.sort_by,
            search_time_ms=search_time_ms,
            field_selection=search_input.field_selection
        )
    
    def _parse_single_result(self, hit: Dict[str, Any]) -> Optional[SearchResult]:
        """Parse a single search hit into SearchResult."""
        try:
            source = hit.get('_source', {})
            
            # Extract and process authors
            authors = self._extract_authors(source.get('Persons', []))
            
            # Extract publication type
            pub_type_data = extract_publication_type(source.get('PublicationType'))
            pub_type = None
            if pub_type_data:
                pub_type = PublicationType(**pub_type_data)
            
            # Extract source name (handle various formats)
            source_name = extract_source_name(source.get('Source'))
            # If that didn't work, try SourceTitle
            if not source_name:
                source_name = source.get('SourceTitle')
            
            # Create result object with smart defaults
            result = SearchResult(
                id=hit.get('_id', ''),
                title=source.get('Title', 'No title'),
                authors=authors,
                year=source.get('Year'),
                abstract=truncate_text(
                    source.get('Abstract'), 
                    settings.DEFAULT_ABSTRACT_LENGTH
                ),
                source=source_name,
                publication_type=pub_type,
                doi=source.get('DOI'),
                keywords=self._extract_keywords(source.get('Keywords', source.get('FreeKeywords'))),
                score=hit.get('_score', 0.0)
            )
            
            # Add optional fields if using fuller field selection
            if hasattr(self, '_include_extended_fields') and self._include_extended_fields:
                result.subtitle = source.get('Subtitle')
                result.language = source.get('Language')
                result.publisher = source.get('Publisher')
                result.volume = source.get('Volume')
                result.issue = source.get('Issue')
                result.pages = source.get('Pages')
            
            return result
            
        except Exception as e:
            # Log error but don't fail the whole search
            print(f"Error parsing result {hit.get('_id', 'unknown')}: {e}")
            return None
    
    def _extract_authors(self, persons_data: Any) -> List[Author]:
        """Extract minimal author information from Persons array.
        
        NOTE: The Persons field is very large with lots of nested data.
        We only extract the essentials to keep responses manageable.
        """
        authors = []
        
        # Handle case where persons_data might not be a list
        if not persons_data or not isinstance(persons_data, list):
            return authors
        
        # Limit processing to first 20 persons to avoid huge processing
        # (some papers have 100+ authors)
        persons_to_process = persons_data[:20] if len(persons_data) > 20 else persons_data
        
        for person in persons_to_process:
            try:
                # Use our utility to extract minimal info
                author_info = extract_author_info(person)
                
                # Only include authors (not editors, supervisors, etc.) 
                # unless specifically requested
                if author_info.get('role') == 'Author' or len(authors) == 0:
                    author = Author(**author_info)
                    authors.append(author)
                    
            except Exception as e:
                # Skip problematic entries
                # Could log this for debugging: print(f"Skipping person: {e}")
                continue
        
        # Sort by order
        authors.sort(key=lambda a: a.order)
        
        # Limit number of authors for display
        max_authors = 10  # Could make this configurable
        if len(authors) > max_authors:
            # Keep first n-1 authors and add "et al." indicator
            authors = authors[:max_authors-1]
            # Add a special author entry to indicate truncation
            authors.append(Author(
                name="et al.",
                role="Author",
                order=999
            ))
        elif len(persons_data) > 20:
            # We didn't process all persons, add indicator
            authors.append(Author(
                name=f"et al. ({len(persons_data) - 20} more)",
                role="Author",
                order=999
            ))
        
        return authors
    
    def _extract_keywords(self, keywords_data: Any) -> Optional[List[str]]:
        """Extract keywords from various formats."""
        if not keywords_data:
            return None
        
        # If it's already a list of strings, return as-is
        if isinstance(keywords_data, list):
            result = []
            for item in keywords_data:
                if isinstance(item, str):
                    result.append(item)
                elif isinstance(item, dict) and 'Value' in item:
                    # Handle {'Value': 'keyword'} format
                    result.append(item['Value'])
            return result if result else None
        
        return None
    
    def _generate_search_suggestions(self, search_input: SearchInput) -> List[str]:
        """Generate helpful suggestions when no results are found."""
        suggestions = []
        
        # Check if filters might be too restrictive
        if search_input.filters:
            if search_input.filters.years:
                suggestions.append("Try broadening the year range or removing year filter")
            if search_input.filters.authors:
                suggestions.append("Try searching for authors individually")
            if search_input.filters.publication_types:
                suggestions.append("Remove publication type filter")
            if search_input.filters.keywords:
                suggestions.append("Use fewer required keywords")
                
        # Check if search is too specific
        if search_input.fields_to_search != ["all"]:
            suggestions.append("Search in all fields instead of specific fields")
            
        # Context-aware suggestions for Chalmers database
        if not suggestions:
            suggestions.extend([
                "Use more general search terms",
                "Check spelling of author names or technical terms",
                "Remove filters to broaden the search",
                "Remember: this database only contains Chalmers-affiliated publications"
            ])
            
        # Add task-specific guidance
        if search_input.query and ("rank" in search_input.query.lower() or "most" in search_input.query.lower() or "top" in search_input.query.lower()):
            suggestions.append("Note: This tool cannot rank or count publications. Consider searching broadly and sampling results.")
            
        # Add source-specific suggestions
        if search_input.filters and search_input.filters.sources:
            suggestions.append("For journal names, try partial matches (e.g., 'IEEE' instead of full name)")
            
        return suggestions
    
    async def _arun(self, *args, **kwargs):
        """Async version not implemented."""
        raise NotImplementedError("Async search not supported")