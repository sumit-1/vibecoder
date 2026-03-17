"""Gemini client and tool declarations for Vibecoder."""

from pathlib import Path

import google.generativeai as genai
from dotenv import load_dotenv
from google.generativeai.types import FunctionDeclaration, Tool

from .tools import get_tool_handlers

load_dotenv()

MODEL = "gemini-3-flash-preview"

FUNCTION_DECLARATIONS = [
    {
        "name": "read_file",
        "description": "Read the full contents of a file. Path is relative to workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to workspace"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "read_file_lines",
        "description": "Read a specific line range from a file (1-based inclusive).",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to workspace"},
                "start_line": {"type": "integer", "description": "First line (1-based)"},
                "end_line": {"type": "integer", "description": "Last line (1-based)"},
            },
            "required": ["path", "start_line", "end_line"],
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a file with the given content.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to workspace"},
                "content": {"type": "string", "description": "Full file content to write"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "search_replace",
        "description": "Find and replace text in a file. Set use_regex true for regex pattern.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to workspace"},
                "old_text": {"type": "string", "description": "Text or regex pattern to find"},
                "new_text": {"type": "string", "description": "Replacement text"},
                "replace_all": {"type": "boolean", "description": "Replace all occurrences (default: false)"},
                "use_regex": {"type": "boolean", "description": "Treat old_text as regex (default: false)"},
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "grep",
        "description": "Search for a regex pattern in files. Returns matches with line numbers. Path can be file or directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File or directory path relative to workspace"},
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "context_lines": {"type": "integer", "description": "Lines of context before/after each match (default: 0)"},
            },
            "required": ["path", "pattern"],
        },
    },
    {
        "name": "search",
        "description": "Plain-text search across files in workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text to search for"},
                "path": {"type": "string", "description": "Directory to search in (default: .)"},
                "file_pattern": {"type": "string", "description": "Glob filter for filenames (e.g. *.py)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "find_files",
        "description": "Find files by glob pattern (e.g. *.py, **/test_*.js).",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern for filenames"},
                "path": {"type": "string", "description": "Directory to search in (default: .)"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "count_lines",
        "description": "Get line count for file(s). Path can be file or directory. Include stats for code/blank/comment breakdown.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File or directory path relative to workspace"},
                "include_stats": {"type": "boolean", "description": "Include code/blank/comment breakdown (default: false)"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_directory",
        "description": "List files and folders in a directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path (default: .)"},
            },
            "required": [],
        },
    },
    {
        "name": "create_directory",
        "description": "Create a directory and parent directories if needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path relative to workspace"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "delete_file",
        "description": "Delete a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to workspace"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "move_file",
        "description": "Rename or move a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Source file path"},
                "destination": {"type": "string", "description": "Destination path"},
            },
            "required": ["source", "destination"],
        },
    },
    {
        "name": "file_exists",
        "description": "Check if a file or directory exists.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to workspace"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "run_command",
        "description": (
            "Run a short-lived shell command (e.g. python script.py, pip install, tsc). "
            "Kills the process after timeout seconds (default 15). "
            "Do NOT use for servers or interactive commands — use run_command_background instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {"type": "integer", "description": "Max seconds before the process is killed (default: 15)"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "run_command_background",
        "description": (
            "Start a long-running or interactive command in the background (e.g. npm start, uvicorn, psql). "
            "Returns immediately after capture_seconds with the PID and any initial output. "
            "Use this for servers, watchers, database CLIs, or any command that does not exit on its own."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to start"},
                "capture_seconds": {"type": "number", "description": "Seconds to collect initial output before detaching (default: 5)"},
            },
            "required": ["command"],
        },
    },
]


def get_model(api_key: str | None = None) -> genai.GenerativeModel:
    """Create and return a GenerativeModel with tools. Uses GEMINI_API_KEY env if api_key not provided."""
    key = api_key or __import__("os").environ.get("GEMINI_API_KEY")
    if not key:
        raise ValueError(
            "GEMINI_API_KEY not set. Set it in environment or pass api_key=..."
        )
    genai.configure(api_key=key)
    tools = [
        Tool(function_declarations=[FunctionDeclaration(**fd) for fd in FUNCTION_DECLARATIONS]),
    ]
    return genai.GenerativeModel(MODEL, tools=tools)


def execute_tool(workspace: Path, name: str, args: dict) -> str:
    """Execute a tool by name and return result as string. Handles errors."""
    handlers = get_tool_handlers(workspace)
    if name not in handlers:
        return f"Unknown tool: {name}"
    try:
        result = handlers[name](**args)
        return str(result)
    except Exception as e:
        return f"Error: {e}"
