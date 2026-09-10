#!/usr/bin/env python3
"""Safely set keys in the hosted .env, reading KEY=VALUE lines from stdin.

Values are read from stdin rather than argv so secrets never land in shell
history or the process list.

Appending with `echo >>` has bitten this deployment before: the file had no
trailing newline, so the new assignment fused onto the previous value and broke
both variables. This rewrites the file line by line instead, replacing a key in
place if it already exists, and validates the result before exiting.

Usage:
    printf 'GOOGLE_OAUTH_CLIENT_ID=xxx\\nGOOGLE_OAUTH_CLIENT_SECRET=yyy\\n' \\
      | sudo python3 set-env-key.py
"""
import os
import re
import sys

PATH = os.environ.get("ENV_PATH", "/opt/studyflows/.env")
NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

updates: dict[str, str] = {}
for raw in sys.stdin.read().splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    if "=" not in line:
        sys.exit(f"stdin line is not KEY=VALUE: {line[:40]!r}")
    name, value = line.split("=", 1)
    name = name.strip()
    if not NAME_RE.fullmatch(name):
        sys.exit(f"invalid key name: {name!r}")
    updates[name] = value.strip()

if not updates:
    sys.exit("nothing to set: stdin had no KEY=VALUE lines")

with open(PATH, "r", encoding="utf-8") as fh:
    lines = fh.read().split("\n")

seen: set[str] = set()
out: list[str] = []
for line in lines:
    stripped = line.strip()
    if stripped and not stripped.startswith("#") and "=" in stripped:
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            # Replace in place so ordering and comments stay stable.
            if key not in seen:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
            continue
    out.append(line)

# Drop trailing blanks so appended keys sit directly after the last assignment.
while out and not out[-1].strip():
    out.pop()
for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")

text = "\n".join(out) + "\n"
with open(PATH, "w", encoding="utf-8") as fh:
    fh.write(text)

# Re-parse and report what the loader will actually see.
parsed: dict[str, str] = {}
bad: list[tuple[int, str]] = []
for lineno, line in enumerate(text.split("\n"), start=1):
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    if "=" not in stripped:
        bad.append((lineno, stripped))
        continue
    key, value = stripped.split("=", 1)
    if not NAME_RE.fullmatch(key.strip()):
        bad.append((lineno, stripped))
        continue
    parsed[key.strip()] = value

for key in updates:
    got = parsed.get(key)
    state = f"set, {len(got)} chars" if got else "MISSING OR EMPTY"
    print(f"{key}: {state}")
print("total keys:", len(parsed))
if bad:
    print("MALFORMED LINES:", bad)
    sys.exit(1)
print("env file OK")
