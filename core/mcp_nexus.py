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
    print(f"[SYSTEM] Booting MCP Nexus (Date: 2026-04-30)...")

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

    async def test_server(name, params):
        print(f"\n--- [SYSTEM] Testing {name} MCP ---")
        try:
            # Shield against infinite node hangs during startup
            async def _connect():
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools = await session.list_tools()
                        print(f"[SUCCESS] {name} Tools: {[t.name for t in tools.tools]}")
            
            await asyncio.wait_for(_connect(), timeout=15.0)
            
        except asyncio.TimeoutError:
            print(f"[FATAL ERROR] {name} MCP: Connection timed out after 15 seconds. Process skipped.")
        except Exception as e:
            print(f"[FATAL ERROR] {name} MCP: {e}")
            if hasattr(e, 'exceptions'):
                for idx, sub_e in enumerate(e.exceptions):
                    print(f"   -> Sub-exception {idx}: {sub_e}")

    await test_server("Filesystem", fs_params)
    await test_server("Sequential Thinking", seq_params)
    await test_server("Google Drive", gdrive_params)

if __name__ == "__main__":
    asyncio.run(connect_to_mcps())