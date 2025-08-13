"""Tool registry for easy access to all tools."""
from typing import List, Dict, Any, Optional
from elasticsearch import Elasticsearch

from .persons import PersonsSearchTool
from .projects import ProjectsSearchTool
from .organizations import OrganizationsSearchTool
from .publications import PublicationsSearchTool
from ..config.settings import settings


def get_all_tools(
    es_client: Optional[Elasticsearch] = None,
    index_name: Optional[str] = None
) -> List[Any]:
    """
    Get all available tools configured with the provided Elasticsearch client.
    
    Args:
        es_client: Elasticsearch client instance. If None, creates one from settings.
        index_name: Index name to use. If None, uses default from settings.
        
    Returns:
        List of configured LangChain tools
    """
    # Create ES client if not provided
    if es_client is None:
        es_client = settings.get_es_client()
    
    # Use default index if not provided
    if index_name is None:
        index_name = settings.ES_INDEX
    
    # Initialize all tools
    tools = [
        # Index-specific tools only - unified_search removed to avoid confusion
        PublicationsSearchTool(es_client=es_client, index_name="research-publications-static"),
        PersonsSearchTool(es_client=es_client, index_name="research-persons-static"),
        ProjectsSearchTool(es_client=es_client, index_name="research-projects-static"),
        OrganizationsSearchTool(es_client=es_client, index_name="research-organizations-static"),
    ]
    
    return tools


def get_tool_by_name(
    name: str,
    es_client: Optional[Elasticsearch] = None,
    index_name: Optional[str] = None
) -> Optional[Any]:
    """
    Get a specific tool by name.
    
    Args:
        name: Tool name (e.g., "unified_search")
        es_client: Elasticsearch client instance
        index_name: Index name to use
        
    Returns:
        The requested tool or None if not found
    """
    tools = get_all_tools(es_client=es_client, index_name=index_name)
    
    for tool in tools:
        if tool.name == name:
            return tool
    
    return None


def get_tools_descriptions() -> Dict[str, str]:
    """
    Get a dictionary of tool names and their descriptions.
    
    Useful for understanding what tools are available.
    
    Returns:
        Dict mapping tool names to descriptions
    """
    # Create temporary tools just to get metadata
    tools = get_all_tools()
    
    return {
        tool.name: tool.description
        for tool in tools
    }