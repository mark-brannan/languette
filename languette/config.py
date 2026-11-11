"""`languette config`: list languette's options, or set or unset them, a row for each one
changed, ✓ or ✗, in the doctor's format. Exits 1 on any ✗ (docs/design/config.md).

The host stays the owner: for Claude Code every read and write goes through `claude plugin
configure`, and this writes no file itself. A value is judged before anything is written, all of
them together, so a refused one leaves every option as it was: a switch must be exactly `true` or
`false`, as run.py reads it, and any other value goes through its guard's own loader
(languette/loaders.py). Claude Code keeps no unset, so `--unset` writes the option's default. Like
the doctor, this sits outside the guard pipeline. Standard library only.
"""

import json
import os
import shutil
import sys

from languette import host, loaders
from languette.host import FAIL, OK


class Refused(Exception):
    """A setting not written: the option it names and why."""


def _claude(*args, stdin=None):
    """`claude` run with args, as install runs it: (stdout, None) on exit 0, else (None, what went wrong)."""
    claude = shutil.which("claude")
    if not claude:
        return None, "the claude command is not on PATH"
    r, why = host.call(claude, *args, stdin=stdin)
    if why or r.returncode != 0:
        return None, why or host.first_line(r)
    return r.stdout, None


def plugin(cwd):
    """The id of the languette install in effect for cwd; Refused when there is none."""
    try:
        inst = host.in_effect(host.installs(host.settings_files(cwd)), cwd)
    except host.Unreadable as e:
        raise Refused("Claude Code", f"{e}, so whether languette is installed is unknown")
    if not inst:
        raise Refused("Claude Code", "languette is not installed for this directory; run languette install")
    return inst.get("id") or host.PLUGIN


def options(pid):
    """(name -> its schema, name -> its value as a string, the names set) as the host has them."""
    out, why = _claude("plugin", "configure", pid, "--json")
    try:
        got = json.loads(out) if out is not None else None
        schema, inputs, configured = got["schema"], got["inputs"], set(got["configured"])
        if not (isinstance(schema, dict) and isinstance(inputs, dict)):
            raise TypeError
    except (ValueError, KeyError, TypeError):
        raise Refused("Claude Code", why or "`claude plugin configure --json` printed no options it could read")
    return schema, {k: v if isinstance(v, str) else host.env_value(v) for k, v in inputs.items()}, configured


def default(spec):
    """An option's default as the host stores it: a string, "" when the manifest gives none."""
    return host.env_value(spec["default"]) if spec.get("default") is not None else ""


def judged(name, value, schema, env):
    """Refused naming why the guard would not take `value` for `name`."""
    spec = schema.get(name)
    if spec is None:
        raise Refused(name, "languette has no such option; languette config lists them")
    if spec.get("type") == "boolean":
        if value not in ("true", "false"):
            raise Refused(name, f"is a switch, exactly true or false; {value!r} would leave the gate as if unset")
        return
    why = loaders.option(name, value, env)
    if why:
        raise Refused(name, why)


def _list(pid):
    schema, inputs, configured = options(pid)
    where = host.tilde(host.user_settings())
    shown = {name: inputs.get(name, default(spec)) or "(empty)" for name, spec in schema.items()}
    width, vwidth = max(map(len, shown), default=0), max(map(len, shown.values()), default=0)
    for name, value in shown.items():
        print(f"{name:<{width}}  {value:<{vwidth}}  {'set in ' + where if name in configured else 'default'}")
    return 0


def _set(pid, pairs, unset):
    schema, inputs, _ = options(pid)
    values = {}
    for pair in pairs:
        name, eq, value = pair.partition("=")
        if not eq:
            raise Refused(pair, "is not name=value")
        values[name] = value
    for name in unset:
        if name not in schema:
            raise Refused(name, "languette has no such option; languette config lists them")
        values[name] = default(schema[name])
    env = host.guard_env(host.installed_options(os.getcwd()))
    for name, value in values.items():
        judged(name, value, schema, env)
    said, why = _claude("plugin", "configure", pid, "--values-stdin", stdin=json.dumps(values))
    if why:
        raise Refused("Claude Code", why)
    for name, value in values.items():
        was = inputs.get(name, default(schema[name]))
        print(f"{OK} {name}: {was or '(empty)'} → {value or '(empty)'}" + (" (its default)" if name in unset else ""))
    print(f"{OK} Claude Code: {next((ln.strip() for ln in said.splitlines() if ln.strip()), 'saved')}")
    return 0


def main(pairs=(), unset=()):
    """`languette config`: no pairs and nothing unset lists every option; else each name=value is
    set and each unset name goes back to its default, all of them or none."""
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    try:
        pid = plugin(os.getcwd())
        return _set(pid, pairs, unset) if pairs or unset else _list(pid)
    except Refused as e:
        label, why = e.args
        print(f"{FAIL} {label}: {why}; nothing written" if pairs or unset else f"{FAIL} {label}: {why}")
        return 1
    except OSError as e:
        print(f"{FAIL} config: the current directory is unreadable ({e.strerror or e})")
        return 1
