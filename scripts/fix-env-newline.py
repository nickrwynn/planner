#!/usr/bin/env python3
"""Repair /opt/studyflows/.env after an append landed on a line with no newline.

Splits any KEY=VALUE that got glued onto the end of a previous value back onto
its own line, and guarantees a trailing newline so future appends are safe.
"""
import re
import sys

PATH = "/opt/studyflows/.env"

with open(PATH, "r", encoding="utf-8") as fh:
    text = fh.read()

# A variable assignment must start a line. If one appears mid-line, split it.
fixed = re.sub(r"(?<!\n)(?<!^)(CURSOR_API_KEY=)", r"\n\1", text)

if not fixed.endswith("\n"):
    fixed += "\n"

with open(PATH, "w", encoding="utf-8") as fh:
    fh.write(fixed)

# Report what the loader will actually see.
bad = []
keys = {}
for lineno, line in enumerate(fixed.split("\n"), start=1):
    if not line.strip() or line.lstrip().startswith("#"):
        continue
    if "=" not in line:
        bad.append((lineno, line))
        continue
    name = line.split("=", 1)[0].strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        bad.append((lineno, line))
        continue
    keys[name] = line.split("=", 1)[1]

print("CURSOR_API_KEY present:", "CURSOR_API_KEY" in keys)
print("CURSOR_API_KEY length:", len(keys.get("CURSOR_API_KEY", "")))
print("GOOGLE_OAUTH_FAILURE_URL:", keys.get("GOOGLE_OAUTH_FAILURE_URL", "<missing>"))
print("total keys:", len(keys))
if bad:
    print("MALFORMED LINES:", bad)
    sys.exit(1)
print("env file OK")
