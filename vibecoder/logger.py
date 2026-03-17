"""Session logger for Vibecoder — records every LLM exchange to a file."""

import time
from datetime import datetime
from pathlib import Path


_DIVIDER = "=" * 80
_THIN    = "-" * 80


class SessionLogger:
    """Writes a full debug log for one vibecoder session.

    Creates ~/.vibecoder/logs/session_YYYYMMDD_HHMMSS.log
    Everything is flushed immediately so the file is readable while the
    session is still running (useful for `tail -f` debugging).
    """

    def __init__(self, workspace: Path, system_prompt: str) -> None:
        log_dir = Path.home() / ".vibecoder" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = log_dir / f"session_{ts}.log"
        self._start = time.monotonic()
        self._fh = self.log_path.open("w", encoding="utf-8")

        self._section(_DIVIDER)
        self._line("VIBECODER SESSION LOG")
        self._line(f"Started  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._line(f"Workspace: {workspace}")
        self._section(_DIVIDER)
        self._blank()
        self._section("SYSTEM PROMPT", thin=True)
        self._line(system_prompt)
        self._blank()

    # ------------------------------------------------------------------
    # Public logging methods
    # ------------------------------------------------------------------

    def log_user_message(self, message: str) -> None:
        self._section(_DIVIDER)
        self._line("USER MESSAGE")
        self._section(_DIVIDER)
        self._line(message)
        self._blank()

    def log_turn_start(self, turn: int) -> None:
        self._section(_THIN)
        self._line(f"  turn {turn + 1}")
        self._section(_THIN)
        self._blank()

    def log_llm_text(self, text_parts: list[str]) -> None:
        """Log any raw text the LLM emitted alongside tool calls."""
        if not text_parts:
            return
        self._section("LLM TEXT (alongside tool calls)", thin=True)
        self._line("\n".join(text_parts))
        self._blank()

    def log_tool_call(self, name: str, args: dict) -> None:
        self._section(f"TOOL CALL  ▶  {name}", thin=True)
        for key, value in args.items():
            str_val = str(value)
            if "\n" in str_val:
                self._line(f"  {key}:")
                for ln in str_val.splitlines():
                    self._line(f"    {ln}")
            else:
                self._line(f"  {key}: {str_val!r}")
        self._blank()

    def log_tool_result(self, name: str, result: str) -> None:
        self._section(f"TOOL RESULT  ◀  {name}", thin=True)
        stripped = result.strip()
        if stripped:
            for ln in stripped.splitlines():
                self._line(f"  {ln}")
        else:
            self._line("  (empty)")
        self._blank()

    def log_final_response(self, response: str) -> None:
        self._section(_DIVIDER)
        self._line("FINAL LLM RESPONSE")
        self._section(_DIVIDER)
        self._line(response)
        self._blank()

    def log_error(self, tag: str, error: str) -> None:
        self._section(f"ERROR — {tag}", thin=True)
        self._line(error)
        self._blank()

    def close(self) -> None:
        elapsed = time.monotonic() - self._start
        self._section(_DIVIDER)
        self._line(f"SESSION END  —  elapsed: {elapsed:.1f}s")
        self._section(_DIVIDER)
        self._fh.close()

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "SessionLogger":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _line(self, text: str) -> None:
        self._fh.write(text + "\n")
        self._fh.flush()

    def _blank(self) -> None:
        self._fh.write("\n")
        self._fh.flush()

    def _section(self, title: str, thin: bool = False) -> None:
        if thin:
            self._fh.write(f"--- {title} ---\n")
        else:
            self._fh.write(title + "\n")
        self._fh.flush()
