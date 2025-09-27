import os  # Import operating system interface module
import uvicorn  # Import ASGI server for running FastAPI/Starlette applications
from starlette.middleware.cors import CORSMiddleware  # Import CORS middleware for handling cross-origin requests
import asyncio
import traceback
import json
from dataclasses import dataclass
from typing import Any
import aiohttp
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from fastmcp import FastMCP, Context
from mcp.types import ToolAnnotations
from fastmcp.exceptions import ToolError
from aiohttp import ClientTimeout
from markdownify import markdownify
from lxml.html import defs, fromstring, tostring
from lxml.html.clean import Cleaner
import os
from datetime import datetime
from pydantic import BaseModel, Field
from smithery.decorators import smithery
from smithery.utils.config import parse_config_from_query_string
import params as params


# Configuration data model - corresponds to fields in smithery.yaml
class Config(BaseModel):
    """Configuration model, corresponding to configuration fields in smithery.yaml"""
    default_proxy_url: str = ""
    default_proxy_login: str = ""
    default_proxy_password: str = ""
    unlocker_proxy_url: str = ""
    unlocker_proxy_login: str = ""
    unlocker_proxy_password: str = ""


"""Create and return FastMCP server instance"""
# Create FastMCP server instance
mcp = FastMCP(
    name="Scrape",
    instructions="""
        The parse_with_ai_selectors method uses proxy or unlocker to crawl and parse web pages according to user needs, with output format options: "html", "links", "Markdown"
    """
)

@dataclass
class ProxyConfig:
    """Proxy configuration data class, containing proxy server connection information"""
    proxy_url: str
    login: str
    password: str
    

class ScrapeRetryException(Exception):
    """Web scraping retry exception, used to trigger retry mechanism when scraping fails"""
    pass

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), enabled=True, meta={"author": "tom", "version": "v1.0"})
async def parse_with_ai_selectors( 
                                    url: params.URL,
                                    render: params.RENDER, 
                                    output_format: params.OUTPUT_FORMAT,
                                    query_string: str,
                                    ctx:Context
                                    ) -> str:
    """
    Use proxy or unlocker to crawl and parse web pages
    
    Parameters:
        url: The URL of the web page to parse
        render: Proxy configuration selector ("Unlocker" for unlocker, other values for regular proxy)
        output_format: Output format ("html", "links", "MarkDown")
        
    """
    
    try:
        # Parse configuration parameters
        config_dict = parse_config_from_query_string(query_string)
        config = Config(**config_dict)  # Use Pydantic to validate configuration
        ctx.info("print:"+query_string)
        # Get proxy configuration from session configuration
        
        if render == "Unlocker":
            # Priority use unlocker proxy from smithery configuration
            proxy_url = config.unlocker_proxy_url 
            proxy_login = config.unlocker_proxy_login 
            proxy_password = config.unlocker_proxy_password 
            
            thor_mcp_myProxyConfig = ProxyConfig(
                proxy_url=proxy_url,
                login=proxy_login,
                password=proxy_password,
            )
        else:
            # Priority use default proxy from smithery configuration
            proxy_url = config.default_proxy_url 
            proxy_login = config.default_proxy_login 
            proxy_password = config.default_proxy_password 
            
            thor_mcp_myProxyConfig = ProxyConfig(
                proxy_url=proxy_url,
                login=proxy_login,
                password=proxy_password,
            )
        
        # Verify proxy configuration parameters cannot be empty
        if not thor_mcp_myProxyConfig.proxy_url or not thor_mcp_myProxyConfig.login or not thor_mcp_myProxyConfig.password:
            raise ToolError(f"Proxy configuration parameters cannot be empty, note: unlocker and proxy accounts are not interchangeable")
        
        thor_mcp_html = ""
        thor_mcp_isCatch=False # Default cache disabled, cache is only for debugging use, as feedback on AI is unstable
        if thor_mcp_isCatch:
            # First check if there is an HTML file for today
            thor_mcp_today = datetime.now().strftime("%Y%m%d")
            thor_mcp_save_dir = "html_snapshots"
            os.makedirs(thor_mcp_save_dir, exist_ok=True)
            # Clean special characters from URL and limit filename length
            thor_mcp_clean_url = url.split("//")[-1]
            for char in [
                "?", ",", "/", "\\", ":", "*", '"', "<", ">", "|", 
                "%", "=", "&", "+", ";", "@", "#", "$", "^", "`", 
                "{", "}", "[", "]", "'",
            ]:
                thor_mcp_clean_url = thor_mcp_clean_url.replace(char, "_")
            # Limit total filename length to 200 characters
            thor_mcp_max_length = 200 - len(thor_mcp_today) - 1  # Subtract date and separator length
            thor_mcp_htmlName = f"{thor_mcp_today}_{thor_mcp_clean_url[:thor_mcp_max_length]}"
            thor_mcp_filename = f"{thor_mcp_save_dir}/{thor_mcp_htmlName}.html"

            if os.path.exists(thor_mcp_filename):
                try:
                    with open(thor_mcp_filename, "r", encoding="utf-8") as f:
                        thor_mcp_html = f.read()
                    print(f"Read HTML from local cache: {thor_mcp_filename}")
                except IOError as e:
                    raise ToolError(f"Failed to read cache file")

            else:
                thor_mcp_html = await scrape(url, thor_mcp_myProxyConfig)
                if not thor_mcp_html:
                    raise ToolError(f"Web scraping failed, unable to get content")
                
                try:
                    with open(thor_mcp_filename, "w", encoding="utf-8") as f:
                        f.write(thor_mcp_html)
                    print(f"HTML saved to {thor_mcp_filename}")
                except IOError as e:
                    raise ToolError(f"Failed to save HTML file")

        else:
            # When cache is disabled, still save HTML but use different directory and second-level timestamp filename
            thor_mcp_now = datetime.now().strftime("%Y%m%d%H%M%S")
            thor_mcp_save_dir = "html_temp"
            os.makedirs(thor_mcp_save_dir, exist_ok=True)
            # Clean special characters from URL and limit filename length
            thor_mcp_clean_url = url.split("//")[-1]
            for char in [
                "?", ",", "/", "\\", ":", "*", '"', "<", ">", "|", 
                "%", "=", "&", "+", ";", "@", "#", "$", "^", "`", 
                "{", "}", "[", "]", "'",
            ]:
                thor_mcp_clean_url = thor_mcp_clean_url.replace(char, "_")
            # Limit total filename length to 200 characters
            thor_mcp_max_length = 200 - len(thor_mcp_now) - 1  # Subtract timestamp and separator length
            thor_mcp_htmlName = f"{thor_mcp_now}_{thor_mcp_clean_url[:thor_mcp_max_length]}"
            thor_mcp_filename = f"{thor_mcp_save_dir}/{thor_mcp_htmlName}.html"

            thor_mcp_html = await scrape(url, thor_mcp_myProxyConfig)
            if not thor_mcp_html:
                raise ToolError(f"Web scraping failed, unable to get content")
            
            try:
                with open(thor_mcp_filename, "w", encoding="utf-8") as f:
                    f.write(thor_mcp_html)
                print(f"HTML temporarily saved to {thor_mcp_filename}")
            except IOError as e:
                raise ToolError(f"Failed to save temporary HTML file")
        
        # Process content and return result
        try:
            thor_mcp_result = get_content(thor_mcp_html, output_format)
            if not thor_mcp_result:
                raise ToolError(f"Content processing failed: Unable to convert content to {output_format} format")
            return thor_mcp_result
        except Exception as e:
            raise ToolError(f"Error occurred during content processing")
    
    
    except Exception as e:
        # Catch other unexpected exceptions
        raise ToolError(f"Unexpected error occurred while parsing web page")

@retry(
        reraise=True,
        # Maximum of 3 attempts
        stop=stop_after_attempt(3),
        # Exponential backoff algorithm, multiplier 1, minimum wait time 4 seconds, maximum wait time 10 seconds
        wait=wait_exponential(multiplier=1, min=4, max= 5),
    )
async def scrape_with_retry(url: str, myProxyConfig: ProxyConfig) -> str:
    """
    Web scraping method with retry mechanism, records detailed information for each retry

    Parameters:
        url: URL address to scrape
        myProxyConfig: Proxy configuration object

    Returns:
        Returns web page content text on success, throws ScrapeRetryException on failure

    Exceptions:
        ScrapeRetryException: Thrown when request fails
    """

    # Get proxy URL from proxy configuration object
    proxy = myProxyConfig.proxy_url
    # Create proxy authentication object using login name and password from proxy configuration
    proxy_auth = aiohttp.BasicAuth(
        login=myProxyConfig.login,
        password=myProxyConfig.password,
    )
    headers = {"X-Render-Type": "html", "X-Wait-Second": "10"}
    timeout = ClientTimeout(total=120)

    # Create asynchronous HTTP client session
    async with aiohttp.ClientSession(
        headers=headers,  
        timeout=timeout, 
        connector=aiohttp.TCPConnector(),  
        max_field_size=32768,  
    ) as session:
        try:
            # Use session to initiate GET request
            async with session.get(
                url,  # Target URL
                proxy=proxy,  # Use proxy
                proxy_auth=proxy_auth,  # Use proxy authentication
                ssl=False,  # Disable SSL verification
            ) as response:
                # Check if response status code is 200 (success)
                if response.status == 200:
                    # Return response text content
                    return await response.text()
                else:
                    # Construct error message containing status code and URL
                    error_msg = f"Status code: {response.status}, URL: {url}"
                    # Throw retry exception
                    raise ScrapeRetryException(error_msg)

        except aiohttp.ClientError as e:
            error_msg = f"HTTP client error"
            raise ScrapeRetryException(error_msg)

        except asyncio.TimeoutError:
            error_msg = (
                f"Request timeout: 60 seconds"
            )
            raise ScrapeRetryException(error_msg)

        except Exception as e:
            error_msg = f"Unknown error:"
            raise ScrapeRetryException(error_msg)

async def scrape(url: str, myProxyConfig: ProxyConfig) -> str:
    """
    Web scraping method

    Parameters:
        url: URL address to scrape
        myProxyConfig: Proxy configuration object

    Returns:
        Returns web page content text on success, returns empty string on failure
    """
    try:
        result = await scrape_with_retry(url, myProxyConfig)
        return result
    except ScrapeRetryException:
        return ""

def clean_html(html: str) -> str:
    """Clean HTML string"""
    cleaner = Cleaner(
        scripts=True,
        kill_tags=["nav", "svg", "footer", "noscript", "script", "form"],
        style=True,
        remove_tags=[],
        safe_attrs=list(defs.safe_attrs) + ["idx"],
        inline_style=True,
        links=True,
        meta=False,
        embedded=True,
        frames=False,
        forms=False,
        annoying_tags=False,
        page_structure=False,
        javascript=True,
        comments=True,
    )
    return cleaner.clean_html(html)

def strip_html(thor_mcp_html: str) -> str:
    """Simplify HTML string, remove unnecessary elements, attributes and redundant content"""
    
    import re
    
    # Call clean_html function for initial cleaning (assuming the function is already defined externally)
    thor_mcp_cleaned_html = clean_html(thor_mcp_html)
    
    # Parse the cleaned HTML string into XML tree structure
    thor_mcp_html_tree = fromstring(thor_mcp_cleaned_html)

    # Traverse all elements in the HTML tree (including nested descendant elements)
    for thor_mcp_element in thor_mcp_html_tree.iter():
        # Remove style attribute (inline styles) from all elements
        if "style" in thor_mcp_element.attrib:
            del thor_mcp_element.attrib["style"]  # Use del statement to delete element attribute

        
        if (
            (
                not thor_mcp_element.attrib  # No attributes
                or (len(thor_mcp_element.attrib) == 1 and "idx" in thor_mcp_element.attrib)  # Or only contains idx attribute
            )
            and not thor_mcp_element.getchildren()  # No child elements
            and (not thor_mcp_element.text or not thor_mcp_element.text.strip())  # No text or blank text
            and (not thor_mcp_element.tail or not thor_mcp_element.tail.strip())  # No tail text or blank tail
        ):
            # Get parent element (may be None if it's the root element)
            thor_mcp_parent = thor_mcp_element.getparent()
            
            # Only remove if parent element exists
            if thor_mcp_parent is not None:
                # Remove current element from parent's tree structure
                thor_mcp_parent.remove(thor_mcp_element)

        # Convert processed XML tree back to HTML string
        return tostring(thor_mcp_html_tree, encoding='unicode')

    # Remove elements containing "footer" or "hidden" in class or id
    thor_mcp_xpath_query = (
        ".//*[contains(@class, 'footer') or contains(@id, 'footer') or "
        "contains(@class, 'hidden') or contains(@id, 'hidden')]"
    )
    # Use XPath query to find all elements that need to be removed
    thor_mcp_elements_to_remove = thor_mcp_html_tree.xpath(thor_mcp_xpath_query)
    # Traverse all elements that need to be removed
    for thor_mcp_element in thor_mcp_elements_to_remove:
        # Get the parent element of the current element
        thor_mcp_parent = thor_mcp_element.getparent()
        # Only perform removal if parent element exists
        if thor_mcp_parent is not None:
            # Remove current element from parent element
            thor_mcp_parent.remove(thor_mcp_element)

    # Reserialize HTML tree to string
    thor_mcp_stripped_html = tostring(thor_mcp_html_tree, encoding="unicode")
    # Replace multiple spaces with single space
    thor_mcp_stripped_html = re.sub(r"\s{2,}", " ", thor_mcp_stripped_html)
    # Replace consecutive newlines with empty string
    thor_mcp_stripped_html = re.sub(r"\n{2,}", "", thor_mcp_stripped_html)
    return thor_mcp_stripped_html

def extract_links_with_text(thor_mcp_html: str, thor_mcp_base_url: str | None = None) -> list[str]:
    """
    Extract links with display text from HTML
    
    Parameters:
        thor_mcp_html (str): Input HTML string
        thor_mcp_base_url (str | None): Base URL for converting relative URLs to absolute URLs
                            If None, relative URLs remain unchanged
    
    Returns:
        list[str]: List of links in format [display text] URL
    """
    # Use lxml's fromstring function to parse HTML string into XML tree structure
    thor_mcp_html_tree = fromstring(thor_mcp_html)
    
    # Initialize empty list to store formatted links
    thor_mcp_links = []

    # Traverse all <a> tags containing href attribute (XPath selector)
    for thor_mcp_link in thor_mcp_html_tree.xpath("//a[@href]"):
        # Get value of href attribute (link target address)
        thor_mcp_href = thor_mcp_link.get("href")
        # Get all text content within the tag (including child tag text), and remove leading/trailing whitespace
        thor_mcp_text = thor_mcp_link.text_content().strip()

        # Only process when both href and text exist (filter empty links or empty text)
        if thor_mcp_href and thor_mcp_text:
            # Skip empty text or pure whitespace text (although strip() is used, prevent special whitespace characters)
            if not thor_mcp_text:
                continue

            # Skip in-page anchor links (starting with #)
            if thor_mcp_href.startswith("#"):
                continue

            # Skip JavaScript pseudo-links
            if thor_mcp_href.startswith("javascript:"):
                continue

            # Convert URL when base_url is provided and it's a relative path (starting with /)
            if thor_mcp_base_url and thor_mcp_href.startswith("/"):
                # Remove trailing slash from base_url to avoid double slash issue
                thor_mcp_base = thor_mcp_base_url.rstrip("/")
                # Concatenate into absolute URL
                thor_mcp_href = f"{thor_mcp_base}{thor_mcp_href}"

            # Add formatted link to result list: [text] URL
            thor_mcp_links.append(f"[{thor_mcp_text}] {thor_mcp_href}")

    # Return list of all qualified links
    return thor_mcp_links

def get_content(thor_mcp_content: str, thor_mcp_output_format: str) -> str:
    """
    Extract content from response and convert to appropriate format
    
    Parameters:
        thor_mcp_content: Response content string
        thor_mcp_output_format: Output format ("html", "links", or other formats converted to markdown) 
    
    Returns:
        Formatted content string
    """
    
    if thor_mcp_output_format == "html": 
        return thor_mcp_content
    if thor_mcp_output_format == "links":
        thor_mcp_links = extract_links_with_text(thor_mcp_content)
        return "\n".join(thor_mcp_links)
    
    thor_mcp_stripped_html = strip_html(thor_mcp_content)  # Simplify HTML content
    return markdownify(thor_mcp_stripped_html) 
    # For other formats, return original content string



# Main program entry point (when running this script directly)
if __name__ == "__main__":  # If current script is the main program entry
    # Get the Starlette app and add CORS middleware
    app = mcp.streamable_http_app()  # Get streamable HTTP application instance
    
    # Add CORS middleware with proper header exposure for MCP session management
    app.add_middleware(  # Add CORS middleware to application
        CORSMiddleware,  # Use CORS middleware class
        allow_origins=["*"],  # Allow cross-origin requests from all origins (should be more restrictive in production)
        allow_credentials=True,  # Allow credentials (such as cookies)
        allow_methods=["GET", "POST", "OPTIONS"],  # Allowed HTTP methods
        allow_headers=["*"],  # Allow all request headers
        expose_headers=["mcp-session-id", "mcp-protocol-version"],  # Allow client to read MCP session ID and protocol version headers
        max_age=86400,  # Preflight request cache time (seconds)
    )

    # Use PORT environment variable
    port = int(os.environ.get("PORT", 8081))  # Get port number from environment variable, default to 8081

    # Run the MCP server with HTTP transport using uvicorn
    uvicorn.run(  # Run server using uvicorn
        app,  # Application instance to run
        host="0.0.0.0",  # Listen on all network interfaces, suitable for containerized deployment
        port=port,  # Use configured port number
        log_level="debug"  # Set log level to debug
    )
