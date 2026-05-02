import asyncio
import os
import sys
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack

# ═══════════════════════════════════════════════════════════════
# MCP Nexus v2: Task-Boundary-Safe Connection Pool
# ═══════════════════════════════════════════════════════════════
# Architecture: A single persistent asyncio event loop runs in a
# dedicated daemon thread. ALL MCP lifecycle operations (init,
# call, shutdown) are dispatched into that loop, ensuring the
# AsyncExitStack and all stdio_client context managers are
# entered, used, and exited within the SAME task context.
# This eliminates the "cancel scope in different task" violation.
# ═══════════════════════════════════════════════════════════════

import threading

NPX_PATH = r"C:\Program Files\nodejs\npx.cmd"
PYTHON_PATH = sys.executable
mcp_env = os.environ.copy()
mcp_env["PATH"] = r"C:\Program Files\nodejs\;" + mcp_env.get("PATH", "")

# ── Internal State (owned exclusively by the nexus loop thread) ──
_sessions = {}
_exit_stack = None
_available_tools = []
_loop = None
_thread = None
_initialized = False
_loop_ready = threading.Event()


def _start_nexus_loop():
    """Runs a dedicated asyncio event loop in a daemon thread."""
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop_ready.set()
    _loop.run_forever()


def _ensure_thread():
    """Lazily starts the nexus event loop thread."""
    global _thread
    if _thread is None or not _thread.is_alive():
        _loop_ready.clear()
        _thread = threading.Thread(target=_start_nexus_loop, daemon=True)
        _thread.start()
        # Block main thread deterministically until loop is running
        _loop_ready.wait()


def _run_in_nexus_loop(coro):
    """Submits a coroutine to the nexus loop and blocks until done.
    This ensures all MCP operations execute in the same task context."""
    _ensure_thread()
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result(timeout=120)


async def _async_initialize():
    """Internal init — runs inside the nexus loop thread's task context."""
    global _exit_stack, _available_tools, _sessions, _initialized
    _exit_stack = AsyncExitStack()
    _sessions = {}
    _available_tools = []

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
        ),
        "Cloud Vanguard": StdioServerParameters(
            command=r"Z:\foundry_project\venv\Scripts\python.exe",
            args=[r"Z:\foundry_project\core\api_mcp.py"]
        ),
        "OSINT Node": StdioServerParameters(
            command=r"Z:\foundry_project\venv\Scripts\python.exe",
            args=[r"Z:\foundry_project\core\web_mcp.py"]
        ),
        "Communications Hub": StdioServerParameters(
            command=r"Z:\foundry_project\venv\Scripts\python.exe",
            args=[r"Z:\foundry_project\core\gmail_mcp.py"]
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

    _initialized = True


async def _async_call_tool(name, args):
    """Internal tool call — runs inside the nexus loop thread's task context."""
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


async def _async_shutdown():
    """Internal shutdown — runs inside the nexus loop thread's task context."""
    global _exit_stack, _initialized
    if _exit_stack:
        await _exit_stack.aclose()
        _exit_stack = None
    _initialized = False


# ═══════════════════════════════════════════════════════════════
# PUBLIC API (thread-safe, callable from any sync/async context)
# ═══════════════════════════════════════════════════════════════

async def initialize_nexus():
    """Public init — dispatches to the nexus loop for task-safe execution."""
    _run_in_nexus_loop(_async_initialize())

async def call_mcp_tool(name, args):
    """Public tool call — dispatches to the nexus loop for task-safe execution."""
    return _run_in_nexus_loop(_async_call_tool(name, args))

def call_mcp_tool_sync(name, args):
    """Synchronous tool call — for use from non-async contexts like process_text."""
    return _run_in_nexus_loop(_async_call_tool(name, args))

def get_tools_for_llm():
    """Returns the list of available tools for mapping."""
    return _available_tools

async def shutdown_nexus():
    """Public shutdown — dispatches to the nexus loop for task-safe execution."""
    _run_in_nexus_loop(_async_shutdown())
    if _loop:
        _loop.call_soon_threadsafe(_loop.stop)

def shutdown_nexus_sync():
    """Synchronous shutdown — for use from non-async contexts."""
    try:
        _run_in_nexus_loop(_async_shutdown())
    except Exception:
        pass
    if _loop:
        _loop.call_soon_threadsafe(_loop.stop)


if __name__ == "__main__":
    # Standalone test functionality
    async def main():
        await initialize_nexus()
        print(f"Registered Tools: {[t.name for t in _available_tools]}")
        await shutdown_nexus()
    asyncio.run(main())