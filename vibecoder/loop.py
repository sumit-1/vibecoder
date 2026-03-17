"""Multi-turn conversation loop for Vibecoder."""

from pathlib import Path

import google.generativeai.protos as protos

from .client import MODEL, execute_tool, get_model
from .logger import SessionLogger


SYSTEM_PROMPT = """You are Vibecoder, a fully autonomous AI coding agent. You operate like a senior engineer sitting at a terminal — you take a task, work through it completely, and only stop when the job is 100% done.

Workspace: {workspace}

═══════════════════════════════════════════════════════
AGENTIC MINDSET — INTERNALIZE THIS COMPLETELY
═══════════════════════════════════════════════════════
• You are FULLY AUTONOMOUS. Do not ask the user for permission to proceed, do not pause to confirm steps, do not ask clarifying questions mid-task. Make sensible decisions and execute.
• Keep going until the ENTIRE task is complete — all files created, all commands run successfully, all errors fixed.
• If something fails, diagnose and fix it yourself. Try alternative approaches. Never give up or hand back a broken state.
• Only produce a text response when the task is FULLY done. That final message is your only output to the user.

═══════════════════════════════════════════════════════
RULES — NEVER BREAK THESE
═══════════════════════════════════════════════════════
1. NEVER output code in your text responses. ALL code goes to files via write_file.
2. After writing any executable file, ALWAYS run it with run_command to verify it works.
3. If run_command shows errors → fix with search_replace or write_file → run again. Repeat until clean.
4. For servers, services, or any command that does not exit by itself → use run_command_background.
5. End with a concise summary (1-3 sentences) of exactly what was built and where it lives. No code in the summary.

═══════════════════════════════════════════════════════
COMPLETION & HANDOFF — PROVIDE INSTRUCTIONS AND RUN
═══════════════════════════════════════════════════════
When generation is complete, make it easy for the user to use what you built:

• For CLI tools: In your final response, include the exact command(s) to run (with any args). Example: "Run: python main.py --input data.csv"

• For web servers: After starting the server with run_command_background, use run_command to open the browser:
  python -c "import webbrowser; webbrowser.open('http://localhost:PORT')"
  Replace PORT with the actual port (e.g. 3000, 8000). Include the URL in your final response.

• For server + client apps: Start the server with run_command_background first, then run the client with run_command. In your final response, list both commands so the user can re-run them later.

• Always end your final response with a clear "How to run" or "Next steps" section containing: commands, URLs, and any CLI arguments. This helps the user run things again without re-reading the whole output.

═══════════════════════════════════════════════════════
WORKFLOW FOR EVERY CODING REQUEST
═══════════════════════════════════════════════════════
  1. Understand the full scope of the task before starting
  2. Plan the files you need (mentally — do not narrate the plan)
  3. write_file → write each file completely
  4. run_command / run_command_background → verify everything works
  5. Fix any errors, re-run, iterate until success
  6. Respond with a short completion summary plus a clear "How to run" / "Next steps" section (commands, URLs, CLI args)

═══════════════════════════════════════════════════════
AVAILABLE TOOLS
═══════════════════════════════════════════════════════
Files     : write_file, search_replace, read_file, read_file_lines, delete_file, move_file
Commands  : run_command (exits on its own, 15s timeout), run_command_background (servers/services — detaches after 5s)
Discovery : list_directory, find_files, grep, search, file_exists, count_lines, create_directory"""


# Terminal labels for live tool-call display
_TOOL_LABELS = {
    "write_file":             ("Writing",      lambda a: a.get("path", "?")),
    "search_replace":         ("Editing",      lambda a: a.get("path", "?")),
    "read_file":              ("Reading",      lambda a: a.get("path", "?")),
    "read_file_lines":        ("Reading",      lambda a: a.get("path", "?")),
    "run_command":            ("Running",      lambda a: a.get("command", "?")),
    "run_command_background": ("Background",   lambda a: a.get("command", "?")),
    "list_directory":         ("Listing",      lambda a: a.get("path", ".")),
    "find_files":             ("Finding",      lambda a: a.get("pattern", "?")),
    "grep":                   ("Searching",    lambda a: a.get("pattern", "?")),
    "search":                 ("Searching",    lambda a: a.get("query", "?")),
    "create_directory":       ("Creating dir", lambda a: a.get("path", "?")),
    "delete_file":            ("Deleting",     lambda a: a.get("path", "?")),
    "move_file":              ("Moving",       lambda a: a.get("source", "?")),
    "file_exists":            ("Checking",     lambda a: a.get("path", "?")),
    "count_lines":            ("Counting",     lambda a: a.get("path", "?")),
}


def _print_tool_start(name: str, args: dict) -> None:
    label, detail_fn = _TOOL_LABELS.get(name, (name, lambda a: ""))
    print(f"  [{label}] {detail_fn(args)}", flush=True)


def _print_tool_result(name: str, result: str) -> None:
    if name in ("run_command", "run_command_background") and result.strip():
        for line in result.strip().splitlines():
            print(f"    | {line}", flush=True)


def _confirm_delete(path: str) -> bool:
    """Ask the user to confirm deletion. Returns True only on explicit 'y'/'yes'."""
    print(f"  [Delete] '{path}'", flush=True)
    while True:
        try:
            answer = input("  Confirm delete? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print(flush=True)
            return False
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no", ""):
            return False
        print("  Please enter y or n.", flush=True)


class Session:
    """A persistent conversation session.

    Holds the full message history so every follow-up message has context
    of everything that happened before — files created, commands run, etc.
    The session log stays open for the entire lifetime of the object.
    """

    def __init__(
        self,
        workspace: Path,
        api_key: str | None = None,
        max_turns_per_message: int = 50,
    ) -> None:
        self.workspace = workspace.resolve()
        self._max_turns = max_turns_per_message
        self._model = get_model(api_key)
        self._system = SYSTEM_PROMPT.format(workspace=str(self.workspace))

        # Conversation history — the system prompt is the first entry and
        # never changes; every subsequent send() appends to this list.
        self._contents: list = [
            protos.Content(role="user", parts=[protos.Part(text=self._system)]),
        ]

        self.log = SessionLogger(self.workspace, self._system)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send(self, user_message: str) -> str:
        """Send one user message and run the agentic tool-call loop.

        Returns the final text response from the model.  The full exchange
        (tool calls, results, model replies) is appended to self._contents
        so the next call to send() has complete context.
        """
        self.log.log_user_message(user_message)
        self._contents.append(
            protos.Content(role="user", parts=[protos.Part(text=user_message)])
        )

        for _turn in range(self._max_turns):
            self.log.log_turn_start(_turn)
            response = self._model.generate_content(self._contents)

            if not response.candidates:
                msg = "No response from model."
                self.log.log_error("no candidates", msg)
                return msg

            parts = response.candidates[0].content.parts
            function_calls: list[tuple[str, dict]] = []
            text_parts: list[str] = []

            for part in parts:
                fc = getattr(part, "function_call", None)
                if fc and getattr(fc, "name", None):
                    args = dict(fc.args) if getattr(fc, "args", None) else {}
                    function_calls.append((getattr(fc, "name", ""), args))
                elif getattr(part, "text", None):
                    text_parts.append(part.text)

            if text_parts:
                self.log.log_llm_text(text_parts)

            # Model finished — no more tool calls
            if not function_calls:
                final = "\n".join(text_parts) if text_parts else "Done."
                self.log.log_final_response(final)
                # Keep the model's reply in context for future messages
                self._contents.append(response.candidates[0].content)
                return final

            # Model wants to call tools — execute them all and feed results back
            self._contents.append(response.candidates[0].content)

            response_parts = []
            for name, args in function_calls:
                self.log.log_tool_call(name, args)

                # Require explicit user confirmation before any deletion
                if name == "delete_file":
                    if not _confirm_delete(args.get("path", "?")):
                        result = "Deletion cancelled by user."
                        print(f"  [Cancelled]", flush=True)
                        self.log.log_tool_result(name, result)
                        response_parts.append(
                            protos.Part(
                                function_response=protos.FunctionResponse(
                                    name=name,
                                    response={"result": result},
                                )
                            )
                        )
                        continue

                _print_tool_start(name, args)
                result = execute_tool(self.workspace, name, args)
                self.log.log_tool_result(name, result)
                _print_tool_result(name, result)
                response_parts.append(
                    protos.Part(
                        function_response=protos.FunctionResponse(
                            name=name,
                            response={"result": result},
                        )
                    )
                )

            self._contents.append(
                protos.Content(role="user", parts=response_parts)
            )

        msg = "Max turns reached. Task may be incomplete."
        self.log.log_error("max turns", msg)
        return msg

    def close(self) -> None:
        self.log.close()

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *_) -> None:
        self.close()


def run(
    user_prompt: str,
    workspace: Path,
    api_key: str | None = None,
    max_turns: int = 50,
) -> str:
    """Single-shot convenience wrapper (used when a prompt is passed as a CLI arg)."""
    with Session(workspace, api_key=api_key, max_turns_per_message=max_turns) as session:
        print(f"  [Log] {session.log.log_path}", flush=True)
        print(flush=True)
        return session.send(user_prompt)
