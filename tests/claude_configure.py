"""`claude plugin configure <id> --json | --values-stdin`, as Claude Code answers it, for
features/config.feature and the doctor's --fix: the schema is this repo's plugin.json, the
values are the user's settings.json pluginConfigs. A boolean takes what the host takes
(true/false, 1/0, yes/no, on/off) and is stored as one; an unknown option is refused.
Usage: python3 claude_configure.py <settings.json> <plugin.json> <args...>"""

import json
import sys

settings_path, manifest, *args = sys.argv[1:]
schema = json.load(open(manifest))["userConfig"]
try:
    settings = json.load(open(settings_path))
except FileNotFoundError:
    settings = {}
if len(args) != 4 or args[:2] != ["plugin", "configure"] or args[3] not in ("--json", "--values-stdin"):
    sys.exit(2)
held = settings.setdefault("pluginConfigs", {}).setdefault(args[2], {}).setdefault("options", {})


def shown(v):
    return "true" if v is True else "false" if v is False else str(v)


if args[3] == "--json":
    inputs = {k: shown(held[k]) if k in held else shown(s["default"]) if "default" in s else "" for k, s in schema.items()}
    print(json.dumps({"pluginId": args[2], "schema": schema, "inputs": inputs,
                      "configured": [k for k in schema if k in held],
                      "unconfigured": [k for k in schema if k not in held]}))
    sys.exit(0)
values = json.load(sys.stdin)
for k, v in values.items():
    if k not in schema:
        print(f'Failed to save configuration: This plugin has no option "{k}".', file=sys.stderr)
        sys.exit(1)
    if schema[k]["type"] == "boolean":
        b = {"true": True, "1": True, "yes": True, "on": True, "false": False, "0": False, "no": False, "off": False}
        if v.lower() not in b:
            print(f"Failed to save configuration: {schema[k]['title']} must be true or false.", file=sys.stderr)
            sys.exit(1)
        held[k] = b[v.lower()]
    else:
        held[k] = v
json.dump(settings, open(settings_path, "w"))
print("Configuration saved. Restart Claude Code to apply it.")
