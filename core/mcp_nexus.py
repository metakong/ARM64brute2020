import asyncio
import os
import sys
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack

# Global registry for tools and sessions to be shared with dsie_core.py
_sessions = {}
_exit_stack = AsyncExitStack()
_available_tools = []

NPX_PATH = r"C:\Program Files\nodejs\npx.cmd"
PYTHON_PATH = sys.executable 
mcp_env = os.environ.copy()
mcp_env["PATH"] = r"C:\Program Files\nodejs\;" + mcp_env.get("PATH", "")

async def initialize_nexus():
    """Initializes persistent connections to all MCP servers."""
    global _available_tools
    print(f"[SYSTEM] Booting MCP Nexus (Date: 2026-05-01)...")

    servers = {
        "Filesystem": StdioServerParameters(
            command=NPX_PATH,
            args=["-y", "@modelcontextprotocol/server-filesystem", r"Z:\foundry_project", r"C:\DSIE_Vault"],
            env=mcp_env
        ),
        "Sequential Thinking": StdioServerParameters(
            command=NPX_PATH,
            args=["-y", "@modelcontextprotocol/server-sequential-thinking"],
            env=mcp_env
        ),
        "Google Drive": StdioServerParameters(
            command=PYTHON_PATH,
            args=[r"Z:\foundry_project\core\gdrive_mcp.py"]
        ),
        "PocketBase Vault": StdioServerParameters(
            command=r"Z:\foundry_project\venv\Scripts\python.exe",
            args=[r"Z:\foundry_project\core\pb_mcp.py"]
        )
    }

    for name, params in servers.items():
        try:
            read_stream, write_stream = await _exit_stack.enter_async_context(stdio_client(params))
            session = await _exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
            
            tools_resp = await session.list_tools()
            for tool in tools_resp.tools:
                _sessions[tool.name] = session
                _available_tools.append(tool)
            print(f"[SUCCESS] {name} Connected.")
        except Exception as e:
            print(f"[ERROR] Failed to connect to {name}: {e}")

async def call_mcp_tool(name, args):
    """Executes a tool call on the corresponding server."""
    session = _sessions.get(name)
    if not session:
        return f"Error: Tool {name} not found."
    try:
        result = await session.call_tool(name, args)
        # Handle the fact that result.content is a list of content blocks
        text_content = []
        for block in result.content:
            if hasattr(block, 'text'):
                text_content.append(block.text)
            else:
                text_content.append(str(block))
        return "\n".join(text_content)
    except Exception as e:
        return f"Error: {e}"

def get_tools_for_llm():
    """Returns the list of available tools for mapping."""
    return _available_tools

async def shutdown_nexus():
    """Gracefully closes all connections."""
    await _exit_stack.aclose()

if __name__ == "__main__":
    # Standalone test functionality
    async def main():
        await initialize_nexus()
        print(f"Registered Tools: {[t.name for t in _available_tools]}")
        await shutdown_nexus()
    asyncio.run(main())