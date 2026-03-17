"""Tool implementations for Vibecoder - all paths sandboxed to workspace."""

import fnmatch
import queue
import re
import subprocess
import threading
import time
from pathlib import Path


def _resolve_path(workspace: Path, path: str) -> Path:
    """Resolve path relative to workspace. Reject path traversal."""
    if not path or path == ".":
        return workspace
    resolved = (workspace / path).resolve()
    try:
        resolved.relative_to(workspace.resolve())
    except ValueError:
        raise PermissionError(f"Path escapes workspace: {path}")
    return resolved


def read_file(workspace: Path, path: str) -> str:
    """Read full file contents."""
    fp = _resolve_path(workspace, path)
    if not fp.is_file():
        raise FileNotFoundError(f"Not a file: {path}")
    return fp.read_text(encoding="utf-8", errors="replace")


def read_file_lines(
    workspace: Path, path: str, start_line: int, end_line: int
) -> str:
    """Read a specific line range (1-based inclusive)."""
    content = read_file(workspace, path)
    lines = content.splitlines()
    start = max(0, start_line - 1)
    end = min(len(lines), end_line)
    return "\n".join(lines[start:end])


def write_file(workspace: Path, path: str, content: str) -> str:
    """Create or overwrite a file."""
    fp = _resolve_path(workspace, path)
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8")
    return f"Wrote {path}"


def search_replace(
    workspace: Path,
    path: str,
    old_text: str,
    new_text: str,
    replace_all: bool = False,
    use_regex: bool = False,
) -> str:
    """Find and replace in a file."""
    content = read_file(workspace, path)
    if use_regex:
        if replace_all:
            new_content, count = re.subn(old_text, new_text, content)
        else:
            new_content, count = re.subn(old_text, new_text, content, count=1)
    else:
        if replace_all:
            count = content.count(old_text)
            new_content = content.replace(old_text, new_text)
        else:
            if old_text in content:
                new_content = content.replace(old_text, new_text, 1)
                count = 1
            else:
                new_content = content
                count = 0
    write_file(workspace, path, new_content)
    return f"Replaced {count} occurrence(s) in {path}"


def grep(
    workspace: Path,
    path: str,
    pattern: str,
    context_lines: int = 0,
) -> str:
    """Search for pattern/regex in files. Returns matches with line numbers."""
    target = _resolve_path(workspace, path)
    try:
        pat = re.compile(pattern)
    except re.error:
        return f"Invalid regex pattern: {pattern}"
    results = []
    files_to_search = []
    if target.is_file():
        files_to_search = [target]
    elif target.is_dir():
        for p in target.rglob("*"):
            if p.is_file() and not p.name.startswith("."):
                files_to_search.append(p)
    else:
        return f"Path not found: {path}"
    for fp in files_to_search:
        try:
            rel = fp.relative_to(workspace)
            text = fp.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if pat.search(line):
                    ln = i + 1
                    start = max(0, ln - 1 - context_lines)
                    end = min(len(lines), ln + context_lines)
                    for j in range(start, end):
                        prefix = ":" if j + 1 == ln else "-"
                        results.append(f"{rel}:{j + 1}{prefix} {lines[j]}")
                    if context_lines > 0 and end < len(lines):
                        results.append("")
        except (OSError, UnicodeDecodeError):
            continue
    return "\n".join(results) if results else f"No matches for '{pattern}'"


def search(
    workspace: Path,
    query: str,
    path: str = ".",
    file_pattern: str | None = None,
) -> str:
    """Plain-text search across files."""
    target = _resolve_path(workspace, path)
    if not target.is_dir():
        target = target.parent
    results = []
    for p in target.rglob("*"):
        if not p.is_file() or p.name.startswith("."):
            continue
        if file_pattern and not fnmatch.fnmatch(p.name, file_pattern):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            if query in text:
                rel = p.relative_to(workspace)
                lines = text.splitlines()
                for i, line in enumerate(lines):
                    if query in line:
                        results.append(f"{rel}:{i + 1}: {line.strip()}")
        except (OSError, UnicodeDecodeError):
            continue
    return "\n".join(results) if results else f"No matches for '{query}'"


def find_files(workspace: Path, pattern: str, path: str = ".") -> str:
    """Find files by glob pattern (e.g. *.py, **/test_*.js)."""
    target = _resolve_path(workspace, path)
    if not target.is_dir():
        target = target.parent
    pattern_leaf = pattern.split("**/")[-1].strip("/") if "**" in pattern else pattern
    matches = []
    for p in target.rglob(pattern_leaf):
        if p.is_file():
            rel = p.relative_to(workspace)
            matches.append(str(rel).replace("\\", "/"))
    return "\n".join(sorted(matches)) if matches else f"No files matching '{pattern}'"


def count_lines(
    workspace: Path,
    path: str,
    include_stats: bool = False,
) -> str:
    """Get line count for file(s). Optional code/blank/comment breakdown."""
    target = _resolve_path(workspace, path)
    files_to_count = []
    if target.is_file():
        files_to_count = [target]
    elif target.is_dir():
        for p in target.rglob("*"):
            if p.is_file() and not p.name.startswith("."):
                files_to_count.append(p)
    else:
        return f"Path not found: {path}"
    total_lines = 0
    total_code = 0
    total_blank = 0
    total_comment = 0
    output_lines = []
    for fp in files_to_count:
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            n = len(lines)
            total_lines += n
            rel = fp.relative_to(workspace)
            if include_stats:
                code = blank = comment = 0
                for line in lines:
                    s = line.strip()
                    if not s:
                        blank += 1
                    elif s.startswith("#") or s.startswith("//") or s.startswith("/*"):
                        comment += 1
                    else:
                        code += 1
                total_code += code
                total_blank += blank
                total_comment += comment
                output_lines.append(
                    f"{rel}: {n} lines (code: {code}, blank: {blank}, comment: {comment})"
                )
            else:
                output_lines.append(f"{rel}: {n} lines")
        except (OSError, UnicodeDecodeError):
            continue
    if include_stats:
        output_lines.append(
            f"\nTotal: {total_lines} lines (code: {total_code}, blank: {total_blank}, comment: {total_comment})"
        )
    else:
        output_lines.append(f"\nTotal: {total_lines} lines")
    return "\n".join(output_lines)


def list_directory(workspace: Path, path: str = ".") -> str:
    """List files and folders in a path."""
    target = _resolve_path(workspace, path)
    if not target.is_dir():
        raise NotADirectoryError(f"Not a directory: {path}")
    entries = []
    for p in sorted(target.iterdir()):
        if p.is_dir():
            entries.append(f"{p.name}/")
        else:
            entries.append(p.name)
    return "\n".join(entries) if entries else "(empty)"


def create_directory(workspace: Path, path: str) -> str:
    """Create a directory (and parents if needed)."""
    fp = _resolve_path(workspace, path)
    fp.mkdir(parents=True, exist_ok=True)
    return f"Created directory {path}"


def delete_file(workspace: Path, path: str) -> str:
    """Delete a file."""
    fp = _resolve_path(workspace, path)
    if not fp.is_file():
        raise FileNotFoundError(f"Not a file: {path}")
    fp.unlink()
    return f"Deleted {path}"


def move_file(workspace: Path, source: str, destination: str) -> str:
    """Rename or move a file."""
    src = _resolve_path(workspace, source)
    dst = _resolve_path(workspace, destination)
    if not src.is_file():
        raise FileNotFoundError(f"Not a file: {source}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    return f"Moved {source} to {destination}"


def file_exists(workspace: Path, path: str) -> bool:
    """Check if a file or directory exists."""
    fp = _resolve_path(workspace, path)
    return fp.exists()


def run_command(workspace: Path, command: str, timeout: int = 15) -> str:
    """Run a short-lived shell command and return its output.

    Kills the process and returns an error if it exceeds *timeout* seconds.
    Use run_command_background for servers or any command that keeps running.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = result.stdout or ""
        err = result.stderr or ""
        if result.returncode != 0:
            return f"Exit code {result.returncode}\n{err}\n{out}".strip()
        return f"{err}\n{out}".strip() if err else out
    except subprocess.TimeoutExpired:
        return (
            f"Command timed out after {timeout}s and was killed.\n"
            "If this is a long-running server or service, use run_command_background instead."
        )


def run_command_background(
    workspace: Path,
    command: str,
    capture_seconds: float = 5.0,
) -> str:
    """Start a long-running command in the background and return immediately.

    Captures output for *capture_seconds* then detaches.  Returns the PID and
    any initial output so the model can confirm the process started correctly.
    Use this for servers (npm start, uvicorn, etc.) or any command that does
    not exit on its own.
    """
    proc = subprocess.Popen(
        command,
        shell=True,
        cwd=str(workspace),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    output_lines: list[str] = []
    line_queue: queue.Queue[str] = queue.Queue()

    def _reader() -> None:
        assert proc.stdout is not None
        for raw in proc.stdout:
            line_queue.put(raw.rstrip())

    reader_thread = threading.Thread(target=_reader, daemon=True)
    reader_thread.start()

    deadline = time.monotonic() + capture_seconds
    while time.monotonic() < deadline:
        try:
            output_lines.append(line_queue.get(timeout=0.1))
        except queue.Empty:
            if proc.poll() is not None:
                break

    rc = proc.poll()

    # Drain any remaining lines already queued
    while True:
        try:
            output_lines.append(line_queue.get_nowait())
        except queue.Empty:
            break

    initial = "\n".join(output_lines)

    if rc is not None:
        # Process already exited within capture_seconds
        status = f"Process exited (code {rc})"
        return f"{status}\n{initial}".strip() if initial else status

    # Still running — detached successfully
    header = f"Process started in background (PID {proc.pid})."
    if initial:
        return f"{header}\nInitial output:\n{initial}"
    return f"{header}\nNo output yet after {capture_seconds:.0f}s — process appears to be running silently."


def get_tool_handlers(workspace: Path):
    """Return a dict mapping tool names to callables."""
    return {
        "read_file":              lambda **kw: read_file(workspace, **kw),
        "read_file_lines":        lambda **kw: read_file_lines(workspace, **kw),
        "write_file":             lambda **kw: write_file(workspace, **kw),
        "search_replace":         lambda **kw: search_replace(workspace, **kw),
        "grep":                   lambda **kw: grep(workspace, **kw),
        "search":                 lambda **kw: search(workspace, **kw),
        "find_files":             lambda **kw: find_files(workspace, **kw),
        "count_lines":            lambda **kw: count_lines(workspace, **kw),
        "list_directory":         lambda **kw: list_directory(workspace, **kw),
        "create_directory":       lambda **kw: create_directory(workspace, **kw),
        "delete_file":            lambda **kw: delete_file(workspace, **kw),
        "move_file":              lambda **kw: move_file(workspace, **kw),
        "file_exists":            lambda **kw: file_exists(workspace, **kw),
        "run_command":            lambda **kw: run_command(workspace, **kw),
        "run_command_background": lambda **kw: run_command_background(workspace, **kw),
    }
