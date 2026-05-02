"""
Thin wrapper around Notion API for this project.
All database writes go through here.
"""

import json
import time
import logging
import requests
from typing import Any, Optional

logger = logging.getLogger(__name__)

NOTION_API_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"
PAGE_SIZE = 100


class NotionClient:
    def __init__(self, api_key: str):
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_API_VERSION,
        }

    def _request(self, method: str, path: str, body: Optional[dict] = None, retries=3) -> dict:
        url = f"{BASE_URL}{path}"
        for attempt in range(retries):
            try:
                resp = requests.request(method, url, headers=self.headers, json=body, timeout=60)
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 5))
                    logger.warning(f"Rate limited, sleeping {wait}s")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                if attempt == retries - 1:
                    raise
                logger.warning(f"Request failed (attempt {attempt+1}): {e}")
                time.sleep(2 ** attempt)
        return {}

    def create_page(self, database_id: str, properties: dict) -> dict:
        body = {
            "parent": {"database_id": database_id},
            "properties": properties,
        }
        return self._request("POST", "/pages", body)

    def update_page(self, page_id: str, properties: dict) -> dict:
        return self._request("PATCH", f"/pages/{page_id}", {"properties": properties})

    def query_database(self, database_id: str, filter_body: Optional[dict] = None,
                       start_cursor: Optional[str] = None) -> dict:
        body: dict[str, Any] = {"page_size": PAGE_SIZE}
        if filter_body:
            body["filter"] = filter_body
        if start_cursor:
            body["start_cursor"] = start_cursor
        return self._request("POST", f"/databases/{database_id}/query", body)

    def query_all(self, database_id: str, filter_body: Optional[dict] = None) -> list[dict]:
        """Paginate through all results."""
        results = []
        cursor = None
        while True:
            data = self.query_database(database_id, filter_body, cursor)
            results.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
        return results

    def get_page(self, page_id: str) -> dict:
        return self._request("GET", f"/pages/{page_id}")


# ── Property builders ───────────────────────────────────────────────────────

def title_prop(value: str) -> dict:
    return {"title": [{"text": {"content": str(value)[:2000]}}]}

def text_prop(value: Optional[str]) -> dict:
    return {"rich_text": [{"text": {"content": str(value)[:2000]}}] if value else []}

def number_prop(value: Optional[float]) -> dict:
    return {"number": float(value) if value is not None else None}

def select_prop(value: Optional[str]) -> dict:
    return {"select": {"name": str(value)} if value else None}

def multi_select_prop(values: list) -> dict:
    return {"multi_select": [{"name": v} for v in values]}

def checkbox_prop(value: bool) -> dict:
    return {"checkbox": bool(value)}

def date_prop(iso_date: Optional[str]) -> dict:
    return {"date": {"start": iso_date} if iso_date else None}

def url_prop(value: Optional[str]) -> dict:
    return {"url": value}

def relation_prop(page_ids: list[str]) -> dict:
    return {"relation": [{"id": pid} for pid in page_ids]}
