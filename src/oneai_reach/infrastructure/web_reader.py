import httpx
from httpx import HTTPStatusError, RequestError
import asyncio

class JinaWebReader:
    """
    Provides an interface for reading and converting websites into markdown strings via Jina's web reader endpoint.
    """

    BASE_URL = "https://r.jina.ai/"

    @staticmethod
    async def fetch_markdown(url: str, timeout: int = 10) -> str:
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
        async with httpx.AsyncClient() as client:
            full_url = JinaWebReader.BASE_URL + url
            try:
                response = await client.get(full_url, timeout=timeout)
                response.raise_for_status()  # Raise error for non-2xx status codes
                return response.text.strip()
            except HTTPStatusError as e:
                raise ValueError(f"HTTP error occurred while fetching {url}: {str(e)}")
            except RequestError as e:
                raise ValueError(f"Request error occurred while fetching {url}: {str(e)}")
            except asyncio.TimeoutError:
                raise ValueError(f"Request timed out while fetching {url}")

# Example Usage #
# asyncio.run(JinaWebReader.fetch_markdown("example.com"))