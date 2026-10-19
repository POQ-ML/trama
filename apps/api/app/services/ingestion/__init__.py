"""Ingestion services — OpenAlex and GitHub connectors + pipeline.

Public surface:
    from app.services.ingestion import OpenAlexConnector, GitHubConnector, IngestionPipeline
"""

from app.services.ingestion.openalex import OpenAlexConnector
from app.services.ingestion.github import GitHubConnector
from app.services.ingestion.pipeline import IngestionPipeline

__all__ = ["OpenAlexConnector", "GitHubConnector", "IngestionPipeline"]
