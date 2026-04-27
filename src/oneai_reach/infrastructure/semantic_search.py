import aiohttp
import asyncio
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

async def fetch_exa_results(query: str, api_key: str) -> List[Dict[str, str]]:
    """
    Fetch search results from Exa's semantic search API.
    """
    url = "https://api.exa.ai/search"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"query": query}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json={"query": query, "useAutoprompt": True}, headers=headers, timeout=15) as response:
            if response.status != 200:
                err_text = await response.text()
                raise Exception(f"Exa API Error: {response.status} {err_text}")
            data = await response.json()
            return [
                {"website": res.get("url"), "text": res.get("title")}
                for res in data.get("results", [])
            ]

async def fetch_duckduckgo_results(query: str) -> List[Dict[str, str]]:
    """
    Fetch search results using DuckDuckGo.
    """
    url = "https://api.duckduckgo.com"
    params = {"q": query, "format": "json", "no_html": 1}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=10) as response:
            if response.status != 200:
                raise Exception(f"DuckDuckGo Search Error: {response.status}")
            data = await response.json()
            return [
                {"website": topic.get("FirstURL"), "text": topic.get("Text")}
                for topic in data.get("RelatedTopics", [])
                if "FirstURL" in topic and "Text" in topic
            ]

async def search_leads_by_intent(query: str, api_key: str = None) -> List[Dict[str, str]]:
    """
    Perform a semantic search for leads based on the query.
    """
    if api_key:
        try:
            return await fetch_exa_results(query, api_key)
        except Exception as exa_error:
            logger.warning(f"Error with Exa API: {exa_error}. Falling back to DuckDuckGo.")
    
    try:
        return await fetch_duckduckgo_results(query)
    except Exception as e:
        logger.error(f"Error with DuckDuckGo fallback: {e}")
        return []
