"""Configuration settings for the research tools."""
import os
from typing import Optional
from elasticsearch import Elasticsearch


class Settings:
    """Application settings loaded from environment variables."""
    
    # Elasticsearch settings
    ES_HOST: str = os.getenv("ES_HOST", "http://localhost:9200")
    ES_USER: Optional[str] = os.getenv("ES_USER")
    ES_PASS: Optional[str] = os.getenv("ES_PASS")
    ES_INDEX: str = os.getenv("ES_INDEX", "research-publications-static")
    
    # Connection settings
    ES_TIMEOUT: int = int(os.getenv("ES_TIMEOUT", "30"))
    ES_VERIFY_CERTS: bool = os.getenv("ES_VERIFY_CERTS", "true").lower() == "true"
    
    # Search settings
    DEFAULT_MAX_RESULTS: int = int(os.getenv("DEFAULT_MAX_RESULTS", "10"))
    MAX_RESULTS_LIMIT: int = int(os.getenv("MAX_RESULTS_LIMIT", "100"))
    DEFAULT_ABSTRACT_LENGTH: int = int(os.getenv("DEFAULT_ABSTRACT_LENGTH", "300"))
    
    @classmethod
    def get_es_client(cls) -> Elasticsearch:
        """Create and return an Elasticsearch client instance."""
        auth = None
        if cls.ES_USER and cls.ES_PASS:
            auth = (cls.ES_USER, cls.ES_PASS)
        
        return Elasticsearch(
            cls.ES_HOST,
            http_auth=auth,
            verify_certs=cls.ES_VERIFY_CERTS,
            request_timeout=cls.ES_TIMEOUT
        )
    
    @classmethod
    def validate(cls) -> None:
        """Validate that required settings are present."""
        if not cls.ES_HOST:
            raise ValueError("ES_HOST environment variable is required")
        if not cls.ES_INDEX:
            raise ValueError("ES_INDEX environment variable is required")


# Create a singleton instance
settings = Settings()