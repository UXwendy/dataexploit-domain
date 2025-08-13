"""Text processing utilities."""
from typing import Optional, List, Dict, Any


def truncate_text(text: Optional[str], max_length: int = 300, suffix: str = "...") -> Optional[str]:
    """
    Truncate text to maximum length with suffix.
    
    Args:
        text: Text to truncate
        max_length: Maximum length (default 300)
        suffix: Suffix to add when truncated (default "...")
    
    Returns:
        Truncated text or None if input was None
    """
    if not text:
        return None
    
    if len(text) <= max_length:
        return text
    
    # Find a good break point (space) near the max length
    truncate_at = max_length - len(suffix)
    last_space = text.rfind(' ', 0, truncate_at)
    
    if last_space > truncate_at * 0.8:  # If we found a space reasonably close
        return text[:last_space] + suffix
    else:
        return text[:truncate_at] + suffix


def extract_author_info(person_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract minimal author information from a Person object.
    
    Args:
        person_data: Full person data from Elasticsearch
        
    Returns:
        Dictionary with just essential author info
    """
    # Extract the PersonData if it's nested
    if "PersonData" in person_data:
        person_info = person_data["PersonData"]
    else:
        person_info = person_data
    
    # Extract role - it might be a string or an object
    role = person_data.get("Role", "Author")
    if isinstance(role, dict):
        role = role.get("NameEng", "Author")
    
    result = {
        "name": person_info.get("DisplayName", "Unknown"),
        "role": role,
        "order": person_data.get("Order", 999),
    }
    
    # Add optional fields if present
    if person_data.get("IsCorresponding"):
        result["is_corresponding"] = True
        
    # Try to extract primary affiliation if available
    if "Affiliation" in person_data:
        result["affiliation"] = person_data["Affiliation"]
    elif "Organizations" in person_data and person_data["Organizations"]:
        # Take first organization name if available
        first_org = person_data["Organizations"][0]
        if "OrganizationData" in first_org:
            org_name = (first_org["OrganizationData"].get("DisplayNameEng") or 
                       first_org["OrganizationData"].get("DisplayName"))
            if org_name:
                result["affiliation"] = org_name
    
    return result


def extract_source_name(source_data: Any) -> Optional[str]:
    """
    Extract source name from various formats.
    
    The Source field can be:
    - A simple string: "Nature"
    - An object with PageStart/PageEnd: {"PageStart": "123", "PageEnd": "145"}
    - Missing entirely
    
    Args:
        source_data: Source data from Elasticsearch
        
    Returns:
        Source name as string or None
    """
    if not source_data:
        return None
    
    if isinstance(source_data, str):
        return source_data
    
    if isinstance(source_data, dict):
        # Try common field names
        for field in ["Name", "DisplayName", "Title", "SourceTitle"]:
            if field in source_data:
                return source_data[field]
        
        # If it's the problematic format from the notebook, return None
        # The actual source name should be in a different field
        if "PageStart" in source_data or "PageEnd" in source_data:
            return None
    
    return None


def extract_publication_type(pub_type_data: Any) -> Optional[Dict[str, Any]]:
    """
    Extract publication type information.
    
    Args:
        pub_type_data: Publication type data from Elasticsearch
        
    Returns:
        Dictionary with code and name, or None
    """
    if not pub_type_data:
        return None
    
    if isinstance(pub_type_data, str):
        return {"name": pub_type_data}
    
    if isinstance(pub_type_data, dict):
        result = {}
        
        # Extract name (try English first)
        name = (pub_type_data.get("DisplayNameEng") or 
                pub_type_data.get("DisplayName") or
                pub_type_data.get("NameEng") or
                pub_type_data.get("Name"))
        if name:
            result["name"] = name
        
        # Extract code if available
        if "Code" in pub_type_data:
            result["code"] = pub_type_data["Code"]
            
        # Extract review status if available
        if "IsReviewed" in pub_type_data:
            result["is_reviewed"] = pub_type_data["IsReviewed"]
        
        return result if result else None
    
    return None


def safe_get_nested(data: Dict[str, Any], path: str, default: Any = None) -> Any:
    """
    Safely get nested dictionary values using dot notation.
    
    Args:
        data: Dictionary to search
        path: Dot-separated path (e.g., "Metrics.CitationCount")
        default: Default value if path not found
        
    Returns:
        Value at path or default
    """
    keys = path.split('.')
    value = data
    
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    
    return value