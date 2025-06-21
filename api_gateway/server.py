#!/usr/bin/env python3
"""
API Gateway MCP Server Implementation

This module implements a Model Context Protocol server that allows:
1. Searching for ConnectWise API endpoints
2. Executing API calls with parameters
3. Sending raw API requests
4. Storing and retrieving frequently used API queries in Fast Memory
"""

import os
import sys
import json
import re
import httpx
import asyncio
import base64
import sqlite3
import logging
from typing import Dict, List, Optional, Any, Union
from mcp.server.fastmcp import FastMCP
from api_gateway.api_db_utils import APIDatabase
from api_gateway.fast_memory_db import FastMemoryDB

# Set up logging
log_dir = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(log_dir, "api_gateway.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("api_gateway")

# Initialize FastMCP server
mcp = FastMCP("api_gateway")

# Global variables
API_URL = None  # Will be set from environment
COMPANY_ID = None
PUBLIC_KEY = None
PRIVATE_KEY = None
AUTH_PREFIX = None  # Will be set from environment
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "connectwise_api.db")
FAST_MEMORY_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fast_memory_api.db")
api_db = None
fast_memory_db = None

# Track if a query came from Fast Memory to avoid asking to save it again
current_query_from_fast_memory = False

class APIError(Exception):
    """Exception raised for API errors"""
    def __init__(self, message, status_code=None, response=None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)

# Initialization Functions

def setup_config():
    """Set up API configuration from environment variables"""
    global API_URL, COMPANY_ID, PUBLIC_KEY, PRIVATE_KEY, AUTH_PREFIX
    
    API_URL = os.environ.get('CONNECTWISE_API_URL')
    COMPANY_ID = os.environ.get('CONNECTWISE_COMPANY_ID')
    PUBLIC_KEY = os.environ.get('CONNECTWISE_PUBLIC_KEY')
    PRIVATE_KEY = os.environ.get('CONNECTWISE_PRIVATE_KEY')
    AUTH_PREFIX = os.environ.get('CONNECTWISE_AUTH_PREFIX', '')
    
    logger.info("ConnectWise API Configuration:")
    logger.info(f"API_URL: {API_URL}")
    logger.info(f"COMPANY_ID: {COMPANY_ID}")
    logger.info(f"PUBLIC_KEY: {PUBLIC_KEY}")
    logger.info(f"PRIVATE_KEY: {'*' * len(PRIVATE_KEY) if PRIVATE_KEY else 'Missing'}")
    logger.info(f"AUTH_PREFIX: {AUTH_PREFIX}")
    
    if not all([API_URL, COMPANY_ID, PUBLIC_KEY, PRIVATE_KEY]):
        logger.error("ConnectWise API configuration incomplete. Please check environment variables.")
        return False
    return True

def initialize_database():
    """Initialize the API database connection"""
    global api_db
    
    # Check if database exists
    if not os.path.exists(DB_PATH):
        logger.error(f"Database file not found at {DB_PATH}")
        logger.error("Please run build_database.py script first to generate the database")
        return False
    
    # Connect to the database
    try:
        api_db = APIDatabase(DB_PATH)
        logger.info("Connected to API database.")
        return True
    except sqlite3.Error as e:
        logger.error(f"Error connecting to database: {e}")
        return False

def initialize_fast_memory():
    """Initialize the Fast Memory database connection"""
    global fast_memory_db
    
    try:
        fast_memory_db = FastMemoryDB(FAST_MEMORY_DB_PATH)
        logger.info("Connected to Fast Memory database.")
        return True
    except sqlite3.Error as e:
        logger.error(f"Error connecting to Fast Memory database: {e}")
        return False

def get_auth_header():
    """Create authorization header for ConnectWise API"""
    if not all([COMPANY_ID, PUBLIC_KEY, PRIVATE_KEY]):
        raise APIError("ConnectWise API configuration incomplete. Check environment variables.")
    
    # Use the configurable prefix
    username = f"{AUTH_PREFIX}{PUBLIC_KEY}"
    password = PRIVATE_KEY
    
    credentials = f"{username}:{password}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    
    # Return the headers with the successful format
    headers = {
        'Authorization': f'Basic {encoded_credentials}',
        'clientId': COMPANY_ID,
        'Content-Type': 'application/json'
    }
    
    return headers

async def make_api_request(
    method: str,
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Make a request to the ConnectWise Manage API
    """
    if not API_URL:
        if not setup_config():
            raise APIError("ConnectWise API URL not configured. Check environment variables.")
        
    url = f"{API_URL}{endpoint}"
    if not headers:
        headers = get_auth_header()
    
    logger.info(f"Making {method} request to: {url}")
    if params:
        logger.info(f"Params: {json.dumps(params)}")
    if data:
        logger.info(f"Data: {json.dumps(data)}")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers, params=params)
            elif method.upper() == "POST":
                response = await client.post(url, headers=headers, json=data)
            elif method.upper() == "PUT":
                response = await client.put(url, headers=headers, json=data)
            elif method.upper() == "PATCH":
                response = await client.patch(url, headers=headers, json=data)
            elif method.upper() == "DELETE":
                response = await client.delete(url, headers=headers)
            else:
                raise APIError(f"Unsupported HTTP method: {method}")
            
            logger.info(f"Response status: {response.status_code}")
            
            response.raise_for_status()
            return response.json() if response.content else {}
            
        except httpx.HTTPStatusError as e:
            error_message = f"HTTP error {e.response.status_code}: {e.response.text}"
            logger.error(error_message)
            raise APIError(error_message, status_code=e.response.status_code, response=e.response)
        except httpx.TimeoutException:
            logger.error("Request timed out. ConnectWise API may be slow to respond.")
            raise APIError("Request timed out. ConnectWise API may be slow to respond.")
        except httpx.RequestError as e:
            logger.error(f"API request error: {str(e)}")
            raise APIError(f"API request failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unknown error: {str(e)}")
            raise APIError(f"Unknown error: {str(e)}")

# Fast Memory Helper Functions

def check_fast_memory(path: str, method: str) -> Optional[Dict[str, Any]]:
    """
    Check if a query exists in Fast Memory.
    
    Args:
        path: API endpoint path
        method: HTTP method
        
    Returns:
        The query if found, None otherwise
    """
    global fast_memory_db, current_query_from_fast_memory
    
    if not fast_memory_db:
        if not initialize_fast_memory():
            logger.error("Failed to initialize Fast Memory database.")
            return None
    
    query = fast_memory_db.find_query(path, method)
    if query:
        # Mark that this query came from Fast Memory
        current_query_from_fast_memory = True
        # Increment usage count
        fast_memory_db.increment_usage(query['id'])
        logger.info(f"Found query in Fast Memory: {path} {method}")
        return query
    
    current_query_from_fast_memory = False
    return None

def format_endpoint_for_saving(method: str, path: str, params: Optional[Dict[str, Any]] = None, data: Optional[Dict[str, Any]] = None) -> str:
    """
    Format endpoint details in a way that can be easily referenced and saved
    
    Args:
        method: HTTP method
        path: API endpoint path
        params: Query parameters
        data: Request body data
    
    Returns:
        Formatted string representation of the endpoint call
    """
    formatted = f"Endpoint: {method.upper()} {path}\n"
    
    if params:
        formatted += "\nQuery Parameters:\n"
        formatted += json.dumps(params, indent=2)
    
    if data:
        formatted += "\nRequest Body:\n"
        formatted += json.dumps(data, indent=2)
        
    formatted += "\n\nTo save this endpoint to Fast Memory:"
    formatted += "\n```"
    formatted += f"\nsave_to_fast_memory("
    formatted += f"\n    path=\"{path}\","
    formatted += f"\n    method=\"{method}\","
    formatted += f"\n    description=\"YOUR DESCRIPTION HERE\","
    
    if params:
        formatted += f"\n    params={json.dumps(params)}"
    else:
        formatted += "\n    params=None"
        
    if data:
        formatted += f",\n    data={json.dumps(data)}"
    
    formatted += "\n)"
    formatted += "\n```"
    
    return formatted

# MCP Tool Implementations

@mcp.tool()
async def search_api_endpoints(query: str, max_results: int = 10) -> str:
    """
    Search for available API endpoints based on a query.
    
    Args:
        query: Search string to find matching endpoints
        max_results: Maximum number of results to return
    """
    if not api_db:
        if not initialize_database():
            return "Error: Failed to initialize API database."
    
    try:
        results = api_db.search_endpoints(query)
        
        if not results:
            return "No API endpoints found matching your query."
        
        formatted_results = []
        for i, endpoint in enumerate(results[:max_results], 1):
            method = endpoint.get('method', '').upper()
            path = endpoint.get('path', '')
            description = endpoint.get('description', 'No description available')
            
            formatted_results.append(f"{i}. {method} {path}\n   {description}")
        
        response = "Found the following API endpoints:\n\n"
        response += "\n\n".join(formatted_results)
        
        if len(results) > max_results:
            response += f"\n\nShowing {max_results} of {len(results)} results. Refine your search for more specific results."
        
        return response
    
    except Exception as e:
        logger.error(f"Error searching API endpoints: {str(e)}")
        return f"Error searching API endpoints: {str(e)}"

@mcp.tool()
async def get_api_endpoint_details(path: str, method: str = "GET") -> str:
    """
    Get detailed information about a specific API endpoint.
    
    Args:
        path: API path (e.g., /service/tickets)
        method: HTTP method (GET, POST, PUT, PATCH, DELETE)
    """
    if not api_db:
        if not initialize_database():
            return "Error: Failed to initialize API database."
    
    try:
        endpoint = api_db.find_endpoint_by_path_method(path, method)
        
        if not endpoint:
            return f"No API endpoint found for {method} {path}."
        
        formatted_details = api_db.format_endpoint_for_display(endpoint)
        return formatted_details
    except Exception as e:
        logger.error(f"Error getting API endpoint details: {str(e)}")
        return f"Error getting API endpoint details: {str(e)}"

@mcp.tool()
async def execute_api_call(
    path: str, 
    method: str = "GET", 
    params: Optional[Dict[str, Any]] = None, 
    data: Optional[Dict[str, Any]] = None
) -> str:
    """
    Execute an API call to the ConnectWise API.
    
    Args:
        path: API endpoint path (e.g., /service/tickets)
        method: HTTP method (GET, POST, PUT, PATCH, DELETE)
        params: Query parameters for the request
        data: Request body data (for POST, PUT, PATCH)
    """
    global current_query_from_fast_memory
    
    if not api_db:
        if not initialize_database():
            return "Error: Failed to initialize API database."
    
    # Check Fast Memory first
    fast_memory_entry = check_fast_memory(path, method)
    if fast_memory_entry:
        # If parameters are not provided, use the ones from Fast Memory
        if params is None and 'params' in fast_memory_entry and fast_memory_entry['params']:
            params = fast_memory_entry['params']
            logger.info(f"Using parameters from Fast Memory: {json.dumps(params)}")
        
        # If data is not provided, use the one from Fast Memory
        if data is None and 'data' in fast_memory_entry and fast_memory_entry['data']:
            data = fast_memory_entry['data']
            logger.info(f"Using data from Fast Memory: {json.dumps(data)}")
    
    try:
        # Verify the endpoint exists in our database
        endpoint = api_db.find_endpoint_by_path_method(path, method)
        if not endpoint:
            return f"Warning: No documented API endpoint found for {method} {path}. Proceeding with caution."
        
        # Execute the API call
        result = await make_api_request(method, path, params, data)
        
        # Format the response
        response = ""
        if isinstance(result, list):
            if len(result) > 10:
                summary = f"Retrieved {len(result)} items. Showing first 10:"
                formatted_data = json.dumps(result[:10], indent=2)
                response = f"{summary}\n\n{formatted_data}\n\n(Response truncated. Full response contained {len(result)} items.)"
            else:
                response = json.dumps(result, indent=2)
        else:
            response = json.dumps(result, indent=2)
        
        # If the query was successful and not from Fast Memory, ask if the user wants to save it
        if not current_query_from_fast_memory:
            # Add a section that shows the endpoint details for easy reference and saving
            endpoint_details = format_endpoint_for_saving(method, path, params, data)
            response += f"\n\n=== SUCCESSFUL API CALL ===\n{endpoint_details}\n\nWould you like to save this query to Fast Memory for quicker access in the future? You can use the save_to_fast_memory function above or reply with a description."
        else:
            # Reset the flag
            current_query_from_fast_memory = False
            
            # Add a note that this query came from Fast Memory
            response = f"[Using query from Fast Memory: {fast_memory_entry['description']}]\n\n" + response
            
        return response
    
    except APIError as e:
        # Reset the flag
        current_query_from_fast_memory = False
        return f"API Error ({e.status_code if e.status_code else 'Unknown'}): {e.message}"
    except Exception as e:
        # Reset the flag
        current_query_from_fast_memory = False
        logger.error(f"Error executing API call: {str(e)}")
        return f"Error executing API call: {str(e)}"

@mcp.tool()
async def natural_language_api_search(query: str, max_results: int = 5) -> str:
    """
    Search for API endpoints using natural language.
    
    Args:
        query: Natural language description of what you're looking for
        max_results: Maximum number of results to return
    """
    if not api_db:
        if not initialize_database():
            return "Error: Failed to initialize API database."
    
    try:
        results = api_db.search_by_natural_language(query, max_results)
        
        if not results:
            return "No API endpoints found matching your query."
        
        formatted_results = []
        for i, endpoint in enumerate(results, 1):
            method = endpoint.get('method', '').upper()
            path = endpoint.get('path', '')
            description = endpoint.get('description', 'No description available')
            category = endpoint.get('category', 'Unknown')
            
            formatted_result = (
                f"{i}. {method} {path}\n"
                f"   Category: {category}\n"
                f"   Description: {description}"
            )
            formatted_results.append(formatted_result)
        
        response = "Based on your query, here are the most relevant API endpoints:\n\n"
        response += "\n\n".join(formatted_results)
        
        # Add suggestion for getting more details
        response += "\n\nTo get more details about a specific endpoint, use get_api_endpoint_details with the path and method."
        
        return response
    
    except Exception as e:
        logger.error(f"Error searching API endpoints: {str(e)}")
        return f"Error searching API endpoints: {str(e)}"

@mcp.tool()
async def list_api_categories() -> str:
    """
    List all available API categories.
    """
    if not api_db:
        if not initialize_database():
            return "Error: Failed to initialize API database."
    
    try:
        categories = api_db.get_categories()
        
        if not categories:
            return "No API categories found."
        
        response = "Available API categories:\n\n"
        response += "\n".join([f"- {category}" for category in categories])
        
        return response
    
    except Exception as e:
        logger.error(f"Error listing API categories: {str(e)}")
        return f"Error listing API categories: {str(e)}"

@mcp.tool()
async def get_category_endpoints(category: str, max_results: int = 20) -> str:
    """
    Get all endpoints for a specific API category.
    
    Args:
        category: Category name (use list_api_categories to see available categories)
        max_results: Maximum number of results to return
    """
    if not api_db:
        if not initialize_database():
            return "Error: Failed to initialize API database."
    
    try:
        endpoints = api_db.get_endpoints_by_category(category)
        
        if not endpoints:
            return f"No endpoints found for category: {category}"
        
        formatted_results = []
        for i, endpoint in enumerate(endpoints[:max_results], 1):
            method = endpoint.get('method', '').upper()
            path = endpoint.get('path', '')
            summary = endpoint.get('summary', 'No summary available')
            
            formatted_results.append(f"{i}. {method} {path}\n   {summary}")
        
        response = f"Endpoints in category '{category}':\n\n"
        response += "\n\n".join(formatted_results)
        
        if len(endpoints) > max_results:
            response += f"\n\nShowing {max_results} of {len(endpoints)} endpoints. Use a higher max_results value to see more."
        
        return response
    
    except Exception as e:
        logger.error(f"Error getting category endpoints: {str(e)}")
        return f"Error getting category endpoints: {str(e)}"

@mcp.tool()
async def send_raw_api_request(
    raw_request: str
) -> str:
    """
    Send a raw API request to the ConnectWise API.
    
    Args:
        raw_request: Raw API request in the format "METHOD /path?params [JSON body]"
                     Example: "GET /service/tickets?conditions=status/name='Open'"
                     Example: "POST /service/tickets { "summary": "Test ticket" }"
    """
    if not setup_config():
        return "Error: Failed to initialize API configuration."
    
    try:
        # Parse the raw request
        parts = raw_request.strip().split(' ', 2)
        
        if len(parts) < 2:
            return "Error: Invalid request format. Use 'METHOD /path [JSON body]'"
        
        method = parts[0].upper()
        path_with_params = parts[1]
        
        # Extract path and params
        if '?' in path_with_params:
            path, query_string = path_with_params.split('?', 1)
            params = {}
            for param in query_string.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    params[key] = value
                else:
                    params[param] = ''
        else:
            path = path_with_params
            params = {}
        
        # Extract body if present
        data = None
        if len(parts) > 2:
            try:
                data = json.loads(parts[2])
            except json.JSONDecodeError:
                return f"Error: Invalid JSON body: {parts[2]}"
        
        # Use the execute_api_call function to handle the API call
        # This ensures Fast Memory checking and saving is consistent
        return await execute_api_call(path, method, params, data)
    
    except Exception as e:
        logger.error(f"Error executing raw API request: {str(e)}")
        return f"Error executing raw API request: {str(e)}"

@mcp.tool()
async def save_to_fast_memory(
    path: str,
    method: str,
    description: str,
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None
) -> str:
    """
    Save an API query to Fast Memory.
    
    Args:
        path: API endpoint path
        method: HTTP method
        description: User-friendly description of the query
        params: Query parameters
        data: Request body data
    """
    if not fast_memory_db:
        if not initialize_fast_memory():
            return "Error: Failed to initialize Fast Memory database."
    
    try:
        query_id = fast_memory_db.save_query(description, path, method, params, data)
        return f"Successfully saved query to Fast Memory with ID {query_id}."
    except Exception as e:
        logger.error(f"Error saving query to Fast Memory: {str(e)}")
        return f"Error saving query to Fast Memory: {str(e)}"

@mcp.tool()
async def list_fast_memory(search_term: Optional[str] = None) -> str:
    """
    List queries saved in Fast Memory.
    
    Args:
        search_term: Optional search term to filter queries
    """
    if not fast_memory_db:
        if not initialize_fast_memory():
            return "Error: Failed to initialize Fast Memory database."
    
    try:
        if search_term:
            queries = fast_memory_db.search_queries(search_term)
            if not queries:
                return f"No queries found in Fast Memory matching '{search_term}'."
        else:
            queries = fast_memory_db.get_all_queries()
            if not queries:
                return "No queries saved in Fast Memory yet."
        
        # Format the queries
        formatted_queries = []
        for i, query in enumerate(queries, 1):
            # Format the parameters and data
            params_str = json.dumps(query.get('params', {}), indent=2) if query.get('params') else "None"
            data_str = json.dumps(query.get('data', {}), indent=2) if query.get('data') else "None"
            
            # Truncate long parameters and data
            if len(params_str) > 100:
                params_str = params_str[:100] + "... (truncated)"
            if len(data_str) > 100:
                data_str = data_str[:100] + "... (truncated)"
            
            formatted_queries.append(
                f"{i}. {query['description']}\n"
                f"   ID: {query['id']}\n"
                f"   Path: {query['method'].upper()} {query['path']}\n"
                f"   Usage Count: {query['usage_count']}\n"
                f"   Parameters: {params_str}\n"
                f"   Data: {data_str}"
            )
        
        response = "Queries saved in Fast Memory:\n\n"
        response += "\n\n".join(formatted_queries)
        
        response += "\n\nTo use a query from Fast Memory, use execute_api_call with the same path and method."
        response += "\nTo delete a query, use delete_from_fast_memory with the query ID."
        
        return response
    
    except Exception as e:
        logger.error(f"Error listing Fast Memory queries: {str(e)}")
        return f"Error listing Fast Memory queries: {str(e)}"

@mcp.tool()
async def delete_from_fast_memory(query_id: int) -> str:
    """
    Delete a query from Fast Memory.
    
    Args:
        query_id: ID of the query to delete
    """
    if not fast_memory_db:
        if not initialize_fast_memory():
            return "Error: Failed to initialize Fast Memory database."
    
    try:
        success = fast_memory_db.delete_query(query_id)
        if success:
            return f"Successfully deleted query with ID {query_id} from Fast Memory."
        else:
            return f"No query found with ID {query_id}."
    except Exception as e:
        logger.error(f"Error deleting query from Fast Memory: {str(e)}")
        return f"Error deleting query from Fast Memory: {str(e)}"

@mcp.tool()
async def clear_fast_memory() -> str:
    """
    Clear all queries from Fast Memory.
    """
    if not fast_memory_db:
        if not initialize_fast_memory():
            return "Error: Failed to initialize Fast Memory database."
    
    try:
        count = fast_memory_db.clear_all()
        return f"Successfully cleared {count} queries from Fast Memory."
    except Exception as e:
        logger.error(f"Error clearing Fast Memory: {str(e)}")
        return f"Error clearing Fast Memory: {str(e)}"

def main():
    """Main entry point for the server"""
    logger.info("Starting ConnectWise API Gateway MCP Server...")
    setup_config()
    initialize_database()
    initialize_fast_memory()

    transport_env = os.environ.get("FASTMCP_TRANSPORT", "stdio").lower()
    transport = (
        "streamable-http"
        if transport_env in {"streamable-http", "http"}
        else "stdio"
    )

    port_env = os.environ.get("FASTMCP_PORT") or os.environ.get("PORT")
    if port_env:
        try:
            mcp.settings.port = int(port_env)
        except ValueError:
            logger.warning(f"Invalid port value '{port_env}', using default {mcp.settings.port}")

    if transport == "streamable-http":
        mcp.settings.host = os.environ.get("FASTMCP_HOST", "0.0.0.0")

    mcp.run(transport=transport)
    
if __name__ == "__main__":
    main()
