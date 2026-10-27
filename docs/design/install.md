# Install

What installing languette is, on any platform. Present tense is the aim;
"(planned: #102)" marks where the code lags. The other design docs: [the
guard pipeline](guard-pipeline.md), [guard rules](guard-rules.md),
[exceptions](exceptions.md), [portability](portability.md).

## Purpose

One command installs languette the way the platform installs tools, one more
wires every coding agent it protects, and the doctor says whether it worked.
A reader skims the README for the block with their platform's heading and
pastes it. Easy, cross-platform install comes before the next host. No block names an interpreter, a cache path or a virtual
environment, and none pipes a download into a shell: languette denies that
shape, and its own install does not ask for an exception.

## The two halves

The package puts `languette` on PATH: the doctor, `scan` and the guards'
runner. The wiring is `languette install [host…]`. For Claude Code it goes
through the plugin marketplace, so the host owns the hooks and their
options. A host with no plugin system gets the fail-closed hook entries
written for it (planned: #102). The halves are complementary: the package
alone protects nothing, and the doctor says so in its first row.

## install

Idempotent. When the host is already wired it says so and writes nothing.
Where the host can write for it, it writes nothing itself; where it must
write, it shows the diff first (planned: #102). It finds its own root from
the executable, never from a host's environment variable. A host it cannot
reach is a ✗ row naming the by-hand path. One row per step, in the doctor's
marks; exit non-zero on any ✗.

## doctor

The install's check, run after it and in CI: each host, the guards on, the
parser rung, a canary through the hooks as installed, and the version. Its
role in configuration is its own design (#274).

## Packaging

Each rung builds on the one below: the Claude Code plugin; the PyPI wheel,
stdlib only, which `pipx` and `uv tool` install as is; the Homebrew tap,
which brings `shfmt` and `gh` with it; then a single-file `.pyz` on each
release, a Nix flake, a devcontainer feature and a GitHub Action (planned:
#102). Every rung pins to a release tag, and every deny names its version.
