"""The verdicts a guard returns, in Claude Code's hookSpecificOutput words,
and the facts a guard may ask for.

A guard's check(doc) reads the call's languette.document.Document and returns
deny(reason), ask(reason), context(text), spend(...) or None; or it is a
generator that yields Needs and Acts and returns one of those. A guard whose
Needs are all known once the command is parsed writes its check as
planned(doc, parse, plan, judge).
Refuse is how a guard's internals say "deny, for this reason" from deep inside
a walk; check catches it and returns deny. Standard library only.
"""

import inspect

from languette.messages import say

# Claude Code's permission_mode values in which a hook's ask reaches no one:
# dontAsk denies every prompt unseen, bypassPermissions skips it. A headless
# run sends its configured mode, so it is not told apart here.
NO_PROMPT = frozenset({"dontAsk", "bypassPermissions"})
# ...and those in which AskUserQuestion reaches no one: dontAsk denies it even
# when allowed; bypassPermissions still shows it.
NO_QUESTION = frozenset({"dontAsk"})

WAY_USER = "That is the user's to run, not an agent's: say what you need and hand them the exact command."


class Refuse(Exception):
    pass


class Need:
    """A fact a guard cannot read from the payload or env: its kind and arguments.
    The runner answers it through languette.world and sends the answer back into
    the guard; a fact that cannot be had is thrown in as the exception world raised.

        git           prog, cwd, *argv    -> stdout, stripped, or None
        forge-api     forge, host, path   -> (status, body) from the forge's client (scan.FORGES),
                                             or (None, None)
        pr-list       cwd, *argv          -> stdout of argv run in cwd, stripped, or None
        which         name                -> the program's path on the env's PATH, or None
        read          path, limit=None    -> the regular file's text, opened non-blocking; ValueError
                                             when it is not regular or past limit bytes
        path          op, path            -> os.path.<op>(path): isdir, isfile, islink, exists,
                                             lexists, realpath; or executable
        physical      path                -> the longest existing prefix of path resolved through
                                             symlinks, the rest appended as written; "" for /
        ruleset-cache slug, branch        -> (mtime, text), or None
        clock                             -> seconds since the epoch
        worktree      op, *args           -> guard-worktrees' per-session record: arrive rec, top
                                             -> (usable, adopt); kept rec -> bool; recorded rec, top -> bool;
                                             scratchpad sid -> dir, or None
        approvals     {label: runs}       -> {label: [AskUserQuestion ids]}: the user's yeses to
                                             each label that no earlier call spent, from the
                                             transcripts alone (world.World._replay); read only
        run           cwd, timeout, *argv -> (exit code, stdout, stderr); raises on a
                                             program that cannot start or times out
        door          session             -> guard-github-issues' per-session door: True when it
                                             stands open, else the id its standing claim holds ("" for
                                             none); read only (world.World._door)
        send-state    session             -> {"subagents": [names, ids], "read": tool or None}
        hostname                          -> this machine's name, as the OS gives it

    worktree arrive writes as it reads, under a rename. An approval is never
    spent here: a guard reads it and returns spend(...), and the runner spends
    it after the verdict.
    """

    __slots__ = ("kind", "args")

    def __init__(self, kind, *args):
        self.kind, self.args = kind, args

    def __eq__(self, other):
        return type(other) is type(self) and (other.kind, other.args) == (self.kind, self.args)

    def __hash__(self):
        return hash((type(self), self.kind, self.args))

    def __repr__(self):
        return f"{type(self).__name__}({self.kind!r}{''.join(', ' + repr(a) for a in self.args)})"


SPEND = "spend"                        # a finding's key: what the runner spends for it
LOST = "lost"                          # a finding's key: its deny reason when the spend is lost


def short(approved, wants):
    """Whether `approved` ({label: ids}) falls short of `wants` ({label: runs})."""
    return any(len(approved[label]) < n for label, n in wants.items())


def spend(kind, *args, lost=None):
    """An ask finding: the call passes once the runner has spent this, after the
    verdict, and only when the verdict lets the call through (run.py). The guard
    spends nothing itself, so no approval goes on a call another guard denies.

        approvals   {label: runs}         one of the user's yeses per run, read again
                                          after the verdict; every guard's labels
                                          are spent together, in one claim, and the
                                          transcript, this call's tool_use in it, is
                                          the record of the spend
        door        claim|take, session, call
                                          guard-github-issues' door, taken for this call

    A spend that can no longer be made (a parallel call took it first) makes the
    call a deny, for the reason `lost`; the runner words a lost approvals spend."""
    if not lost and kind != "approvals":       # a deny with no reason; the guard's crash is one
        raise ValueError(f"spend({kind!r}) needs lost=, its deny reason")
    return {SPEND: [[kind, *args]], **({LOST: lost} if lost else {})}


def approvals(wants):
    """The user's yeses this call may spend, per label: `approved = yield from
    approvals({label: runs})` is {label: AskUserQuestion ids}, the yeses no earlier
    call spent, oldest first. Nothing is written.
    The world's OSError or ValueError, for a payload with no transcript or a
    transcript that can't be read, is raised from here."""
    return (yield Need("approvals", dict(wants)))


def approve(wants, unreadable):
    """For a guard that denies until the user has approved every run:
    `approved, done = yield from approve({label: runs}, unreadable)`. `done` is
    None when the approvals fall short (approved says how far, to tell the user
    what is missing), else a 1-tuple holding the check's result: the ask
    finding spend("approvals", wants) when every label has its runs' worth,
    (deny,) when the transcript could not be read, the reason being
    unreadable(err), the error world raised. One click is one run, whichever
    guard asked: the runner spends every guard's labels in one claim."""
    try:
        approved = yield from approvals(wants)
    except (OSError, ValueError) as e:
        return None, (deny(unreadable(e)),)
    if short(approved, wants):
        return approved, None
    return approved, (spend("approvals", dict(wants)),)


class Act(Need):
    """A write a guard asks for. The runner sends None back at once and does
    every Act through languette.world after the verdict, whatever the verdict;
    one that fails changes nothing.

        ruleset-keep    slug, branch, text  the ruleset cache's entry
        send-keep       session, op, arg    guard-cross-session-send's state (op: clear, read, names)
        worktree-keep   rec, top            a toplevel into guard-worktrees' per-session record
        worktree-leave  rec, text           what the next call may adopt (<rec>.arrive)
        door-open       session             guard-github-issues' door, fresh; any claim dropped
        door-spend      session             that door and its claim, gone
        terms-init      (none)              the default redacted terms file, where none is there
        send-fail       session             guard-cross-session-send's state, as a failed state hook leaves it
    """

    __slots__ = ()


def judged(doc, name, judge, any_call=False):
    """A check for a guard whose judge(doc) gives a deny reason or None: no
    command is no finding (unless `any_call`: the guard judges a call with none, an MCP
    tool's), and a reason is a deny under the guard's name; a judge may instead give a
    verdict, which stands as it is. A judge that is a generator is run to its end, so
    the check is one too."""
    if doc.text is None and not any_call:
        return None
    why = judge(doc)
    return _judged_after(name, why) if inspect.isgenerator(why) else _judged(name, why)


def _judged(name, why):
    if isinstance(why, dict):                  # a verdict of its own: a judge that asked the world
        return why
    return deny(say("judged", guard=name, why=why)) if why else None


def _judged_after(name, gen):
    return _judged(name, (yield from gen))


def planned(doc, parse, plan, judge):
    """A check for a guard that parses once: parse(doc) reads the command, plan
    lists every Need, and judge(parsed, answers) gets the answers keyed by
    Need, with world's exception in place of a fact it could not have."""
    parsed = parse(doc)
    answers = {}
    for need in plan(parsed):
        try:
            answers[need] = yield need
        except Exception as e:  # noqa: BLE001 -- judge decides what a missing fact means
            answers[need] = e
    return judge(parsed, answers)


def deny(reason):
    return {"permissionDecision": "deny", "permissionDecisionReason": reason}


def ask(reason):
    return {"permissionDecision": "ask", "permissionDecisionReason": reason}


def context(text):
    return {"additionalContext": text}


def allow(reason, updated_input):
    """Let the call through with its input rewritten: a redaction, never a loosening."""
    return {"permissionDecision": "allow", "permissionDecisionReason": reason, "updatedInput": updated_input}


def _footer(chained):
    """The chain footer, once, when `chained` (a callable, read here only) says
    the command had more than one segment; nothing when there is no reading."""
    return [say("chain_footer")] if chained is not None and chained() else []


def verdict(event, findings, mode=None, chained=None):
    """The one decision for a call, from every guard's finding: the fields of
    hookSpecificOutput, or None for silence. `findings` is [(guard name, result,
    crashed)] in the order the guards judged. A deny outranks an ask, an ask an
    allow (a redaction), and an ask carries a rewrite along; the first rewrite wins, since two cannot both apply.
    A deny ends with the chain footer when `chained`, a callable read only then, says the
    command had more than one segment (languette.document.Document.chained).
    In a permission `mode` where no one can answer (NO_PROMPT), an ask is a deny that names
    each ask and leaves the call to the user."""
    if event != "PreToolUse":                  # state-keeping events: nothing to decide
        return None
    reasons, asks, allows, notes, rewrites = [], [], [], [], []
    for name, r, _ in findings:
        if not r:
            continue
        if r.get("permissionDecision") == "deny":
            reasons.append(r["permissionDecisionReason"])
        if r.get("permissionDecision") == "ask":
            asks.append((name, r["permissionDecisionReason"]))
        if r.get("permissionDecision") == "allow":
            allows.append(r["permissionDecisionReason"])
        if "updatedInput" in r:
            rewrites.append(r["updatedInput"])
        if r.get("additionalContext"):
            notes.append(r["additionalContext"])
    if reasons:
        return deny("\n\n".join(reasons + _footer(chained)))
    if asks and mode in NO_PROMPT:
        return deny("\n\n".join([say("unattended_ask", guard=n, mode=mode, why=r) for n, r in asks]
                                 + [say("unattended_way")] + _footer(chained)))
    if asks:
        return {**ask("\n\n".join(r for _, r in asks)), **({"updatedInput": rewrites[0]} if rewrites else {})}
    if allows:
        out = {"permissionDecision": "allow", "permissionDecisionReason": "\n\n".join(allows),
               "updatedInput": rewrites[0]}
        return {**out, "additionalContext": "\n\n".join(notes)} if notes else out
    if notes:
        return context("\n\n".join(notes))
    return None
