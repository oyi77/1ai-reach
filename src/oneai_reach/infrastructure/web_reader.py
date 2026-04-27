import httpx
from httpx import HTTPStatusError, RequestError
import asyncio
import logging
from oneai_reach.infrastructure.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)

class JinaWebReader:
    """
    Provides an interface for reading and converting websites into markdown strings via Jina's web reader endpoint.
    """

    BASE_URL = "https://r.jina.ai/"

    @staticmethod
    async def fetch_markdown(url: str, timeout: int = 15) -> str:
        """
        Fetches and cleans the contents of the given URL using Jina's web reader API.

        Args:
            url (str): The URL of the website to fetch.
            timeout (int): Timeout for the HTTP request in seconds.
        
        Returns:
            str: Cleaned markdown content of the webpage.

        Raises:
            ValueError: If the URL is invalid or server responds with an error.
        """
        rate_limiter = get_rate_limiter("jina_reader", calls_per_minute=60)
        await rate_limiter.acquire()
        
        async with httpx.AsyncClient() as client:
            full_url = JinaWebReader.BASE_URL + url
            try:
                response = await client.get(full_url, timeout=timeout)
                response.raise_for_status()
                return response.text.strip()
            except HTTPStatusError as e:
                raise ValueError(f"HTTP error occurred while fetching {url}: {str(e)}")
            except RequestError as e:
                raise ValueError(f"Request error occurred while fetching {url}: {str(e)}")
            except asyncio.TimeoutError:
                raise ValueError(f"Request timed out while fetching {url}")
