import gc
import json
import sys
import urllib.request
import urllib.parse
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server named "PocketBase_Vault"
mcp = FastMCP("PocketBase_Vault")
PB_URL = "http://127.0.0.1:8090/api/collections"

@mcp.tool()
def list_collections() -> str:
    """Returns a list of all available database collections/tables in the PocketBase vault."""
    try:
        req = urllib.request.Request(f"{PB_URL}?perPage=100")
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            collections = [item['name'] for item in data.get('items', [])]
            res = json.dumps({"status": "SUCCESS", "collections": collections})
    except Exception as e:
        res = json.dumps({"status": "ERROR", "message": str(e)})
    gc.collect()
    return res

@mcp.tool()
def query_collection(collection_name: str, filter_string: str = "", max_results: int = 5) -> str:
    """
    Query a specific PocketBase collection. 
    Use filter_string for PocketBase syntax (e.g., 'title ~ "David"').
    """
    try:
        url = f"{PB_URL}/{collection_name}/records?perPage={max_results}"
        if filter_string:
            url += f"&filter={urllib.parse.quote(filter_string)}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            res = json.dumps({"status": "SUCCESS", "records": data.get('items', [])})
    except Exception as e:
        res = json.dumps({"status": "ERROR", "message": str(e)})
    gc.collect()
    return res

@mcp.tool()
def insert_record(collection_name: str, record_json: str) -> str:
    """
    Inserts a new record into a PocketBase collection.
    record_json must be a valid JSON string of the key/value pairs matching the schema.
    """
    try:
        url = f"{PB_URL}/{collection_name}/records"
        data = record_json.encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())
            res = json.dumps({"status": "SUCCESS", "inserted_id": result.get('id')})
    except Exception as e:
        res = json.dumps({"status": "ERROR", "message": str(e)})
    gc.collect()
    return res

if __name__ == "__main__":
    print("Booting DSIE PocketBase MCP on stdio...", file=sys.stderr)
    mcp.run(transport='stdio')
