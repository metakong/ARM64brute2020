import asyncio
import os
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

NPX_PATH = r"C:\Program Files\nodejs\npx.cmd"
PYTHON_PATH = sys.executable 

# Construct the custom environment to bypass the Windows registry
mcp_env = os.environ.copy()
mcp_env["PATH"] = r"C:\Program Files\nodejs\;" + mcp_env.get("PATH", "")

async def connect_to_mcps():
    print(f"[SYSTEM] Booting MCP Nexus (Date: 2026-04-25)...")

    # Define parameters for ALL 3 servers
    fs_params = StdioServerParameters(
        command=NPX_PATH,
        args=["-y", "@modelcontextprotocol/server-filesystem", r"Z:\foundry_project", r"C:\DSIE_Vault"],
        env=mcp_env
    )

    seq_params = StdioServerParameters(
        command=NPX_PATH,
        args=["-y", "@modelcontextprotocol/server-sequential-thinking"],
        env=mcp_env
    )

    gdrive_params = StdioServerParameters(
        command=PYTHON_PATH,
        args=[r"Z:\foundry_project\core\gdrive_mcp.py"]
    )

    # --- Testing Filesystem ---
    print("\n--- [SYSTEM] Testing Filesystem MCP ---")
    try:
        async with stdio_client(fs_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                print(f"[SUCCESS] Filesystem Tools: {[t.name for t in tools.tools]}")
    except Exception as e:
        print(f"[FATAL ERROR] Filesystem MCP: {e}")

    # --- Testing Sequential Thinking ---
    print("\n--- [SYSTEM] Testing Sequential Thinking MCP ---")
    try:
        async with stdio_client(seq_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                print(f"[SUCCESS] Sequential Thinking Tools: {[t.name for t in tools.tools]}")
    except Exception as e:
        print(f"[FATAL ERROR] Sequential Thinking MCP: {e}")

    # --- Testing Google Drive ---
    print("\n--- [SYSTEM] Testing Google Drive MCP ---")
    try:
        async with stdio_client(gdrive_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                print(f"[SUCCESS] Google Drive Tools: {[t.name for t in tools.tools]}")
    except Exception as e:
        print(f"[FATAL ERROR] Google Drive MCP: {e}")
        if hasattr(e, 'exceptions'):
            for idx, sub_e in enumerate(e.exceptions):
                print(f"   -> Sub-exception {idx}: {sub_e}")

if __name__ == "__main__":
    asyncio.run(connect_to_mcps())