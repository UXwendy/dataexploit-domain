"""Base Elasticsearch search tool class."""
import json
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Type, Optional, List

from langchain.tools import BaseTool
from langchain.callbacks.manager import CallbackManagerForToolRun
from elasticsearch import Elasticsearch
from pydantic import BaseModel, Field

from .models import BaseSearchInput, SearchResult


class BaseElasticsearchSearchTool(BaseTool, ABC):
    """Abstract base class for all Elasticsearch search tools."""
    
    # Tool metadata - must be defined by subclasses
    name: str = ""
    description: str = ""
    args_schema: Type[BaseModel] = BaseSearchInput
    handle_tool_error: bool = True
    
    # Elasticsearch client and index
    es_client: Any = Field(exclude=True)
    index_name: str = Field(exclude=True)
    
    def __init__(self, es_client: Elasticsearch, index_name: str):
        """Initialize with ES client and index name."""
        super().__init__(es_client=es_client, index_name=index_name)
    
    def _run(
        self,
        query: str = "",
        max_results: int = 10,
        offset: int = 0,
        sort_by: str = "relevance",
        field_selection: str = "standard",
        run_manager: Optional[CallbackManagerForToolRun] = None,
        **kwargs  # Tool-specific filters
    ) -> str:
        """Execute search and return results as JSON string."""
        start_time = time.time()
        
        try:
            # Build the search request
            search_request = self._build_search_request(
                query=query,
                max_results=max_results,
                offset=offset,
                sort_by=sort_by,
                field_selection=field_selection,
                filters=kwargs
            )
            
            # Execute the search
            raw_results = self.es_client.search(
                index=self.index_name,
                body=search_request
            )
            
            # Transform results based on field selection
            transformed_results = self._transform_results(
                raw_results,
                field_selection
            )
            
            # Build final response
            search_time_ms = int((time.time() - start_time) * 1000)
            
            # Extract facets if present
            facets = None
            if 'aggregations' in raw_results:
                facets = self._extract_facets(raw_results['aggregations'])
            
            result = SearchResult(
                results=transformed_results,
                pagination={
                    "total": raw_results['hits']['total'],
                    "offset": offset,
                    "limit": max_results,
                    "has_more": offset + max_results < raw_results['hits']['total']
                },
                query=query,
                filters_applied=kwargs,
                sort_by=sort_by,
                field_selection=field_selection,
                search_time_ms=search_time_ms,
                facets=facets
            )
            
            return json.dumps(result.model_dump(), indent=2, ensure_ascii=False)
            
        except Exception as e:
            # Return error in consistent format
            error_result = SearchResult(
                results=[],
                pagination={"total": 0, "offset": 0, "limit": max_results, "has_more": False},
                query=query,
                filters_applied=kwargs,
                sort_by=sort_by,
                field_selection=field_selection,
                error=str(e),
                error_type=type(e).__name__
            )
            return json.dumps(error_result.model_dump(), indent=2)
    
    async def _arun(self, *args, **kwargs) -> str:
        """Async version - not implemented."""
        raise NotImplementedError("Async execution not supported")
    
    @abstractmethod
    def _build_search_request(
        self,
        query: str,
        max_results: int,
        offset: int,
        sort_by: str,
        field_selection: str,
        filters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build the Elasticsearch query.
        Must be implemented by each specific tool.
        
        Args:
            query: Search query string
            max_results: Maximum results to return
            offset: Pagination offset
            sort_by: Sort order
            field_selection: Field selection level
            filters: Tool-specific filters
            
        Returns:
            Elasticsearch query DSL
        """
        pass
    
    @abstractmethod
    def _transform_results(
        self,
        raw_results: Dict[str, Any],
        field_selection: str
    ) -> List[Dict[str, Any]]:
        """
        Transform raw Elasticsearch results based on field selection.
        Must be implemented by each specific tool.
        
        Args:
            raw_results: Raw response from Elasticsearch
            field_selection: Field selection level (standard/expanded/full)
            
        Returns:
            List of transformed documents
        """
        pass
    
    def _get_source_fields(self, field_selection: str) -> Optional[List[str]]:
        """
        Get the list of fields to retrieve from Elasticsearch.
        Can be overridden by specific tools.
        
        Args:
            field_selection: Field selection level
            
        Returns:
            List of field names or None (to get all fields)
        """
        # By default, get all fields and filter in transform
        # Specific tools can override to optimize
        return None
    
    def _build_sort_clause(self, sort_by: str) -> List[Dict[str, Any]]:
        """
        Build the sort clause for Elasticsearch.
        Can be overridden by specific tools.
        
        Args:
            sort_by: Sort order
            
        Returns:
            Elasticsearch sort clause
        """
        if sort_by == "relevance":
            return ["_score"]
        elif sort_by == "date_desc":
            # Tools should override with their specific date field
            return [{"_id": "desc"}]
        elif sort_by == "date_asc":
            return [{"_id": "asc"}]
        elif sort_by == "name_asc":
            # Tools should override with their specific name field
            return [{"_id": "asc"}]
        else:
            return ["_score"]
    
    def _extract_facets(self, aggregations: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract facet results from Elasticsearch aggregations.
        
        Args:
            aggregations: Raw aggregations from ES response
            
        Returns:
            Processed facets
        """
        facets = {}
        
        for agg_name, agg_data in aggregations.items():
            if 'buckets' in agg_data:
                # Terms aggregation
                facets[agg_name] = [
                    {
                        "value": bucket['key'],
                        "count": bucket['doc_count']
                    }
                    for bucket in agg_data['buckets']
                ]
            elif 'buckets' in agg_data.get('pi_filter', {}).get('names', {}):
                # Nested aggregation (for PIs)
                facets[agg_name] = [
                    {
                        "value": bucket['key'],
                        "count": bucket['doc_count']
                    }
                    for bucket in agg_data['pi_filter']['names']['buckets']
                ]
            elif 'buckets' in agg_data and isinstance(agg_data['buckets'], dict):
                # Filters aggregation (for status)
                facets[agg_name] = [
                    {
                        "value": status,
                        "count": data['doc_count']
                    }
                    for status, data in agg_data['buckets'].items()
                ]
        
        return facets