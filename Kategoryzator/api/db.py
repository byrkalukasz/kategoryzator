"""Compatibility facade for DB operations.

This module re-exports DB functions from smaller service modules so existing imports
(`import api.db as db`) continue to work unchanged.
"""

from api.services.db_core import (
    init_db,
    normalize_text,
    sanitize_company_id,
)
from api.services.history_service import (
    delete_invoice,
    find_similar,
    find_similar_candidates,
    list_history,
    store_invoice,
)
from api.services.company_config_service import (
    get_company_config,
    upsert_company_config,
)
from api.services.llm_usage_service import (
    get_llm_usage,
    get_llm_usage_report_summary,
    list_llm_usage_clients,
    register_llm_usage,
)

__all__ = [
    "init_db",
    "normalize_text",
    "sanitize_company_id",
    "store_invoice",
    "find_similar",
    "find_similar_candidates",
    "list_history",
    "delete_invoice",
    "get_company_config",
    "upsert_company_config",
    "register_llm_usage",
    "get_llm_usage",
    "list_llm_usage_clients",
    "get_llm_usage_report_summary",
]
