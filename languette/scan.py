"""Shell-text scanner. Nothing here decides anything; it
turns the Bash tool's command string into words a guard judges, and every
ambiguity resolves toward MORE words reaching the guard, never fewer.

Its parts are modules of their own, and the names callers read through
scan are re-exported here under each:
languette.quoting (quotes, heredocs), languette.lexicon (the commands known
by name), languette.ladder (the parser ladder), languette.lexer (the Scan),
languette.cd_tracking, languette.forges, languette.git_calls,
languette.texts (the texts a command runs), languette.stops and
languette.command_rules. A test that stands in for a name sets it where
the name is defined.
"""

from .quoting import heredoc_bodies, strip_heredocs, UNRESOLVED, VAR_REF, _ASSIGN, _heredocs
from .lexicon import (CD, client, CLIENTS, getopt, GH, GIT, GIT_WRAPPERS, GLAB, LAUNCH, listed, operands,
                      PROSE, PROSE_PROCESS, SHELL)
from .ladder import (BASH_TIMEOUT, check, KEYWORD_LEADS, LENGTH_MAX, parse, RunFailed, RUNGS, shfmt,
                     SHFMT_MIN, SHFMT_TIMEOUT, TooBig, TooMany, Unparseable, weight)
from .git_calls import add_options, git_env, git_wrapper, GitCall, long_option, UnreadOption, wrapper_git
from .lexer import Scan, seg_cmd, UNREADABLE, word, word_live
from .forges import (FORGES, gh_api, gh_api_arg, gh_api_path, gh_env_repo, gh_repo, gh_repo_flag, GH_REPO_FLAGS,
                     gh_verb, gl_project, GRAPHQL, GRAPHQL_READ, norm_repo, PAGE, Remote, remote)
from .texts import alone, cmd_index, segments, texts_of, texts_of_command, writes
from .cd_tracking import cd_present, SEP_OPS
from .stops import CTL_HOST, CTL_STOPS, PROGRAMS, SERVICE_STOPS, SYSV_CMDS
from .command_rules import BadRules, ENGINE_MATCH_KEYS, load_rules, match_rule, SHIPPED_MATCH_KEYS
