Reproduced on devbox (alex@devbox.tail1234.ts.net, 100.101.102.103) in
/home/alex/src/project/.worktrees/fix-login-3e482c, Python at
/home/alex/.venv/bin/python; the Windows side sees C:\Users\alex\project.
The scratch directory was /home/alex/.local/state/tmp/session-bd5fc18d-07f3-49c4-b031-f4c7c11271ab.

Steps:
1. `ssh alex@192.168.1.20` (the NAS, nas.local), then `curl http://10.0.0.5:8080/health`.
2. Compare the docker bridge 172.17.0.1, fd12:3456::1 on the tailnet, and the public resolver 8.8.8.8.
3. The old box zephyr-01 billed this to acct-9931; the mirror to acct-1234.
4. Session bd5fc18d-07f3-49c4-b031-f4c7c11271ab, served at http://localhost:3000/.

Mail went to someone@example.net and security@python.org. Range 10.0.0.0/8 was
excluded; 172.32.0.1 and 100.128.0.1 are public. See ~/notes and /home/alex2/other.
