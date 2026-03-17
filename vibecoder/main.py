"""CLI entry point for Vibecoder."""

import argparse
import sys
from pathlib import Path

from .client import MODEL
from .loop import Session, run


# ──────────────────────────────────────────────────────────────────────────────
# Input helpers
# ──────────────────────────────────────────────────────────────────────────────

_EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit", "q"}


def _collect_input() -> str | None:
    """Read a multi-line message from the user.

    Press Enter twice to submit.
    Type 'exit' / 'quit' (or press Ctrl-C / Ctrl-D) to end the session.
    Returns None when the user wants to quit.
    """
    lines: list[str] = []
    while True:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            return None

        if line.strip().lower() in _EXIT_COMMANDS:
            return None

        # Two consecutive blank lines = submit
        if line == "" and lines and lines[-1] == "":
            lines.pop()
            break

        lines.append(line)

    return "\n".join(lines).strip() or None


def _print_separator() -> None:
    print("─" * 60, flush=True)


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Vibecoder — AI coding assistant. Describe what you want built."
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Requirements (omit to enter interactive chat mode)",
    )
    parser.add_argument(
        "--workspace", "-w",
        type=Path,
        default=Path.cwd(),
        help="Workspace directory for all file operations (default: cwd)",
    )
    parser.add_argument(
        "--api-key",
        help="Gemini API key (default: GEMINI_API_KEY env var)",
    )
    args = parser.parse_args()

    workspace: Path = args.workspace.resolve()
    if not workspace.is_dir():
        print(f"Error: workspace is not a directory: {workspace}", file=sys.stderr)
        sys.exit(1)

    # ── Single-shot mode (prompt passed as CLI argument) ──────────────────────
    if args.prompt:
        prompt = " ".join(args.prompt)
        try:
            result = run(user_prompt=prompt, workspace=workspace, api_key=args.api_key)
            print(result)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    # ── Interactive REPL mode ─────────────────────────────────────────────────
    print("Vibecoder — AI Coding Assistant")
    print(f"Model     : {MODEL}")
    print(f"Workspace : {workspace}")
    print("Submit    : press Enter twice")
    print("Quit      : type 'exit' or press Ctrl-C")

    try:
        with Session(workspace, api_key=args.api_key) as session:
            print(f"Log       : {session.log.log_path}")

            while True:
                print()
                prompt = _collect_input()

                if prompt is None:
                    print("\nGoodbye!")
                    break

                print(flush=True)
                try:
                    result = session.send(prompt)
                    print()
                    _print_separator()
                    print(result)
                    _print_separator()
                except KeyboardInterrupt:
                    print("\n[Interrupted — type 'exit' to quit or enter a new message]")

    except KeyboardInterrupt:
        print("\nGoodbye!")
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
