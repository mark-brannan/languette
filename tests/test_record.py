"""The decision record (#82): opt-in, redacted unless asked, never the verdict's
business, whole lines under parallel hooks, 0600, rotated."""

import fcntl
import json
import os
import stat
import time
from concurrent.futures import ThreadPoolExecutor

from languette import record, run, world
from languette.world import World

RM = "rm -rf ~/secret-project && git push"


def _env(tmp_path, raw=False, on=True):
    env = {"HOME": "/home/languette-test", "XDG_STATE_HOME": str(tmp_path / "state"), "PATH": os.environ["PATH"]}
    if on:
        env["CLAUDE_PLUGIN_OPTION_RECORD_DECISIONS"] = "true"
    if raw:
        env["CLAUDE_PLUGIN_OPTION_RECORD_RAW_COMMANDS"] = "true"
    return env


def _payload(command, **kw):
    return json.dumps({"cwd": os.getcwd(), "hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "s1",
                       "tool_use_id": "toolu_1", "tool_input": {"command": command}, **kw})


def _records(tmp_path):
    f = tmp_path / "state" / "languette" / "decisions.jsonl"
    return [json.loads(line) for line in f.read_text().splitlines()] if f.exists() else []


def test_nothing_is_written_unless_turned_on(tmp_path):
    run.respond(_payload(RM), _env(tmp_path, on=False), "guard-recursive-delete")
    assert not (tmp_path / "state").exists()


def test_a_deny_is_recorded_with_the_command_and_reason_whole(tmp_path):
    out = run.respond(_payload(RM), _env(tmp_path), "guard-recursive-delete")
    [rec] = _records(tmp_path)
    assert rec["v"] == 1 and rec["verdict"] == "deny" and json.loads(out)
    [f] = rec["findings"]
    assert f["guard"] == "guard-recursive-delete" and f["decision"] == "deny" and f["reason"]
    assert rec["command"] == {"text": RM, "masked": 0, "programs": ["rm", "git"]}


# Built at run time, as in test_secrets.py, so no literal token sits in the repo.
PAT = "ghp_" + "Zq9kLm2pQ7rXv4TnWb8Yc3Hd5Fg6Js1Ae0Ux"  # gitleaks:allow
PW = "Zq9kLm2pQ7rXv4Tn"  # gitleaks:allow
SECRET = [
    (f"GITHUB_TOKEN={PAT} gh api repos/acme/app", "GITHUB_TOKEN=<secret> gh api repos/acme/app"),
    (f"export OPENAI_API_KEY='{PW}'", "export OPENAI_API_KEY='<secret>'"),
    (f"docker login -u acme --password {PW}", "docker login -u acme --password <secret>"),
    (f"gh auth login --with-token={PW}", "gh auth login --with-token=<secret>"),
    (f"curl -H 'Authorization: Bearer {PW}' https://x", "curl -H 'Authorization: Bearer <secret>' https://x"),
    (f"curl -u acme:{PW} https://x", "curl -u acme:<secret> https://x"),  # gitleaks:allow
    (f"git clone https://acme:{PW}@git.example.com/a.git", "git clone https://acme:<secret>@git.example.com/a.git"),
    (f"echo {PAT}", "echo <secret>"),
    ("mysql -u root -phunter2 db", "mysql -u root -p<secret> db"),  # mask-only: guard-secrets stays silent
    ("echo " + "Ab3" * 12, "echo <secret>"),                          # mask-only: a long mixed-case run
    (f"bash -c 'export T={PAT}'", "bash -c 'export T=<secret>'"),
    (f"cat <<EOF\nDB_PASSWORD={PW}\nEOF", "cat <<EOF\nDB_PASSWORD=<secret>\nEOF"),
]
KEPT = ["git checkout " + "3f2a9c1e" * 5, "rm -rf ~/secret-project && git push", "mkdir -p a/b",
        "cat ~/.ssh/id_rsa", "aws s3 cp x s3://bucket --profile prod", "ls /usr/lib/x86_64-linux-gnu/libpython3.12.so",
        "GITHUB_TOKEN=" + "x" * 40 + " gh api user"]


def test_only_what_the_detector_names_is_masked():
    for before, after in SECRET:
        assert record.mask(before) == (after, 1), before
    for kept in KEPT:
        assert record.mask(kept) == (kept, 0), kept


def test_the_record_masks_the_command(tmp_path):
    run.respond(_payload(f"rm -rf ~/x && echo {PAT}"), _env(tmp_path), "guard-recursive-delete")
    [rec] = _records(tmp_path)
    assert rec["command"]["text"] == "rm -rf ~/x && echo <secret>" and rec["command"]["masked"] == 1
    assert PAT not in json.dumps(rec)


def test_a_reason_is_masked_as_lines_of_data():
    r = {"permissionDecision": "deny", "permissionDecisionReason": f"a\nDB_PASSWORD={PW}\nb"}
    assert record._finding("guard-x", r, False, False)["reason"] == "a\nDB_PASSWORD=<secret>\nb"


def test_a_secret_the_command_does_not_spell_that_way_drops_the_text_not_the_secret(monkeypatch):
    # The shell reads `"gh""p_..."` as one word; the raw text holds no such substring to mask.
    monkeypatch.setattr(record.guard_secrets, "scans", lambda text: [record.secrets.Text(f"DB_PASSWORD={PW}")])
    assert record.mask("echo hi") == (None, 1)


def test_a_masking_failure_leaves_the_verdict_alone(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("detector broke")
    want = run.respond(_payload(RM), _env(tmp_path, on=False), "guard-recursive-delete")
    monkeypatch.setattr(record.secrets, "findings", boom)
    assert run.respond(_payload(RM), _env(tmp_path), "guard-recursive-delete") == want
    [rec] = _records(tmp_path)
    assert rec["command"]["text"] is None and "reason" not in rec["findings"][0]


def test_a_command_every_guard_let_through_is_recorded(tmp_path):
    run.respond(_payload("ls -la"), _env(tmp_path), None)
    [rec] = _records(tmp_path)
    assert rec["verdict"] == "silent" and rec["rung"] and len(rec["findings"]) > 1
    assert {f["decision"] for f in rec["findings"]} == {"none"}


def test_shell_keywords_are_not_programs():
    assert record.programs('for f in *.py; do python3 "$f"; done') == ["python3"]
    assert record.programs("if ! grep -q x f; then rm x; fi") == ["grep", "rm"]
    assert record.programs("case $x in a) rm y;; esac") == ["rm"]


def test_raw_keeps_the_command_and_the_reason(tmp_path):
    run.respond(_payload(RM), _env(tmp_path, raw=True), "guard-recursive-delete")
    [rec] = _records(tmp_path)
    assert rec["command"] == {"raw": RM} and rec["findings"][0]["reason"]


def test_a_refused_parse_names_the_rung(tmp_path):
    run.respond(_payload("echo 'open"), _env(tmp_path), "require-well-formed")
    [rec] = _records(tmp_path)
    assert rec["refused"] and rec["rung"] and rec["verdict"] == "deny"


def test_a_failed_write_leaves_the_verdict_alone(tmp_path):
    (tmp_path / "state").write_text("a file where the directory should be")
    env = _env(tmp_path)
    assert run.respond(_payload(RM), env, "guard-recursive-delete") == \
        run.respond(_payload(RM), _env(tmp_path, on=False), "guard-recursive-delete")


def test_an_unreadable_payload_is_recorded_as_its_deny(tmp_path):
    out = run.respond("not json", _env(tmp_path), None)
    [rec] = _records(tmp_path)
    assert json.loads(out) and rec["verdict"] == "deny" and rec["findings"] == []


def test_an_open_record_directory_is_closed(tmp_path):
    d = tmp_path / "state" / "languette"
    d.mkdir(parents=True, mode=0o755)
    run.respond(_payload("ls"), _env(tmp_path), None)
    assert stat.S_IMODE(d.stat().st_mode) == 0o700


def test_a_short_write_is_finished(tmp_path, monkeypatch):
    real = os.write
    monkeypatch.setattr(os, "write", lambda fd, b: real(fd, b[:7]))
    World(_env(tmp_path), {}).keep({"n": 0, "pad": "x" * 50})
    assert [r["n"] for r in _records(tmp_path)] == [0]


def test_the_file_is_the_users_alone(tmp_path):
    run.respond(_payload("ls"), _env(tmp_path), None)
    f = tmp_path / "state" / "languette" / "decisions.jsonl"
    assert stat.S_IMODE(f.stat().st_mode) == 0o600
    assert stat.S_IMODE(f.parent.stat().st_mode) == 0o700


def test_parallel_writers_leave_whole_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(world, "RECORDS_MAX", 4096)
    w = World(_env(tmp_path), {})
    pad = "x" * 300
    with ThreadPoolExecutor(max_workers=16) as ex:
        list(ex.map(lambda n: w.keep({"n": n, "pad": pad}), range(200)))
    d = tmp_path / "state" / "languette"
    lines = [line for f in (d / "decisions.jsonl", d / "decisions.jsonl.1") if f.exists()
             for line in f.read_text().splitlines()]
    assert all(json.loads(line)["pad"] == pad for line in lines)
    assert (d / "decisions.jsonl").stat().st_size <= 4096


def test_rotation_keeps_one_old_file(tmp_path, monkeypatch):
    monkeypatch.setattr(world, "RECORDS_MAX", 200)
    w = World(_env(tmp_path), {})
    for n in range(20):
        w.keep({"n": n, "pad": "x" * 50})
    d = tmp_path / "state" / "languette"
    assert sorted(p.name for p in d.iterdir()) == ["decisions.jsonl", "decisions.jsonl.1"]
    assert json.loads((d / "decisions.jsonl").read_text().splitlines()[-1])["n"] == 19


def test_a_held_lock_drops_the_record_not_the_call(tmp_path, monkeypatch):
    monkeypatch.setattr(world, "RECORDS_WAIT", 0.05)
    w = World(_env(tmp_path), {})
    w.keep({"n": 0})
    f = tmp_path / "state" / "languette" / "decisions.jsonl"
    with open(f, "a") as holder:
        fcntl.flock(holder, fcntl.LOCK_EX)
        t0 = time.monotonic()
        w.keep({"n": 1})
        assert time.monotonic() - t0 < 1
    assert [r["n"] for r in _records(tmp_path)] == [0]


def test_a_symlink_in_place_of_the_file_is_not_followed(tmp_path):
    d = tmp_path / "state" / "languette"
    d.mkdir(parents=True)
    (d / "decisions.jsonl").symlink_to(tmp_path / "elsewhere")
    World(_env(tmp_path), {}).keep({"n": 0})
    assert not (tmp_path / "elsewhere").exists()


def test_a_guard_name_nothing_has_is_a_deny(tmp_path):
    out = json.loads(run.respond(_payload("echo hi"), _env(tmp_path, on=False), "guard-disk"))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "no guard is named guard-disk" in out["hookSpecificOutput"]["permissionDecisionReason"]
