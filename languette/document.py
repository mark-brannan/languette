"""The call every guard reads: the payload, the env, and the command parsed
once (docs/design/guard-pipeline.md).

Each piece of the parse is computed on first use and kept, a failure too: a
guard that touches a parse that raised gets the same exception, so the parser
ladder runs once per call and no text is scanned twice. A shell text is read
as the shell guards have always read the command: trailing newlines as one,
heredoc bodies stripped. Read-only. Standard library only.
"""

import json

from languette import scan as sw


def _source(text):
    return text.rstrip("\n") + "\n"


class Document:
    __slots__ = ("payload", "env", "event", "tool", "tool_input", "command", "_text", "_memo")

    def __init__(self, payload, env):
        ti = payload.get("tool_input")
        tool = payload.get("tool_name")
        cmd = ti.get("command") if isinstance(ti, dict) else None
        # The command as the shell guards read it: a non-string as `jq -r` prints it.
        text = "" if cmd is None or cmd is False else cmd if isinstance(cmd, str) else json.dumps(cmd)
        fields = {"payload": payload, "env": env, "event": payload.get("hook_event_name") or "PreToolUse",
                  "tool": tool, "tool_input": ti, "command": cmd if tool == "Bash" and isinstance(cmd, str) else None,
                  "_text": text, "_memo": {}}
        for name, value in fields.items():
            object.__setattr__(self, name, value)

    def __setattr__(self, name, value):
        raise AttributeError("a Document is read-only")

    def __delattr__(self, name):
        raise AttributeError("a Document is read-only")

    def _kept(self, key, make):
        memo = self._memo
        if key not in memo:
            try:
                memo[key] = (True, make())
            except Exception as e:  # noqa: BLE001 -- kept, and raised again on every read
                memo[key] = (False, e)
        ok, got = memo[key]
        if not ok:
            raise got
        return got

    @property
    def refusal(self):
        """The scan.Unparseable the ladder or the nested-text cap refuses the
        Bash command with, or None when it reads (or there is no command). Any
        other failure is raised."""
        def read():
            if self.command is None:
                return None
            try:
                sw.check(self.command)
                self.texts()
            except sw.Unparseable as e:
                return e
            return None
        return self._kept(("refusal",), read)

    def scan(self, text):
        """The scan.Scan of `text`, one per text per call. A guard reads it, never changes it."""
        return self._kept(("scan", text), lambda: sw.Scan(text))

    def _heredocs(self, text):
        src = _source(self._text if text is None else text)
        return self._kept(("heredocs", src), lambda: sw._heredocs(src))

    def stripped(self, text=None):
        """`text`, the command when None, with heredoc bodies stripped (scan.strip_heredocs)."""
        return self._heredocs(text)[0]

    def heredocs(self, text=None):
        """[(body, live)] per heredoc in `text`, the command when None (scan.heredocs)."""
        return [(body, not quoted and ("$" in body or "`" in body)) for body, quoted in self._heredocs(text)[1]]

    def heredoc_bodies(self, text=None):
        return [body for body, _ in self._heredocs(text)[1]]

    def texts(self, prose=sw.PROSE, text=None):
        """scan.texts_of `text`, the command when None, heredocs stripped: [(text, nested)]."""
        stripped = self.stripped(text)
        return self._kept(("texts", stripped, prose), lambda: tuple(sw.texts_of(stripped, prose, read=self.scan)))
