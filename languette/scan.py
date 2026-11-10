"""Shell-text scanner. Nothing here decides anything; it
turns the Bash tool's command string into words a guard judges, and every
ambiguity resolves toward MORE words reaching the guard, never fewer.

Its parts are modules of their own, every name read here under one:
languette.quoting (quotes, heredocs), languette.lexicon (the commands known
by name), languette.ladder (the parser ladder), languette.lexer (the Scan),
languette.cd_tracking, languette.forges, languette.git_calls,
languette.texts (the texts a command runs), languette.stops and
languette.command_rules. A test that stands in for a name sets it where
the name is defined.
"""

from .quoting import (ansi_c, heredoc_bodies, heredoc_subs, heredocs, strip_heredocs, UNRESOLVED, VAR_REF,
                      _ASSIGN, _heredocs)
from .lexicon import (CD, client, CLIENTS, EXEC, getopt, GH, GIT, GIT_VALUE, GIT_WRAPPERS, GLAB, LAUNCH,
                      LAUNCH_SUB, listed, LOOP, operands, PM, PROSE, PROSE_PROCESS, RUN, SHELL, WRAP,
                      Wrapper)
from .ladder import (BASH_TIMEOUT, check, KEYWORD_LEADS, LENGTH_MAX, parse, PIP, RunFailed, RUNGS, shfmt,
                     SHFMT_MIN, SHFMT_TIMEOUT, TooBig, TooMany, Unparseable, weight, WEIGHT_MAX)
from .git_calls import (git_call, git_options, git_subcommand, git_verb, git_wrapper, VCSH_ALL, VCSH_VERBS,
                        wrapper_git)
from .lexer import Scan, seg_cmd, UNREADABLE, word, word_live
from .forges import (FORGES, gh_api, gh_api_arg, GH_API_FIELDS, gh_api_path, GH_API_VALUED, gh_method_flag,
                     GH_METHOD_FLAGS, gh_repo_flag, GH_REPO_FLAGS, gh_verb, GhApi, GhArg, gl_project,
                     GLAB_API_FIELDS, GLAB_API_VALUED, norm_repo, PAGE, Remote, remote)
from .texts import (alone, cmd_index, INERT, NESTED_CAP, runs_quoted, segments, shell_heredocs, texts_of,
                    texts_of_command, writes)
from .cd_tracking import cd_present, cwds, SEP_OPS
from .stops import CTL_HOST, CTL_STOPS, PROGRAMS, SERVICE_STOPS, stop_of, SYSV_CMDS, unit_names, unit_test
from .command_rules import BadRules, ENGINE_MATCH_KEYS, load_rules, match_rule, SHIPPED_MATCH_KEYS
