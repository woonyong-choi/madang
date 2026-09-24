"""Stand-in for an agent CLI: replays a stream file and records its call.

Controlled by environment variables:
FAKE_STREAM  file whose lines are written to stdout
FAKE_DUMP    file that receives {"argv", "cwd", "env"} as JSON
FAKE_SLEEP   seconds to sleep after the stream (also starts a child ``sleep``)
FAKE_CHILD   file that receives the pid of that child
FAKE_STDERR  text written to stderr
FAKE_EXIT    exit code
"""

import json
import os
import subprocess
import sys
import time

env = os.environ
if env.get("FAKE_DUMP"):
    keep = {
        k: env[k]
        for k in ("MADANG_PAGE", "MADANG_HOME", "MADANG_CORE_URL")
        if k in env
    }
    with open(env["FAKE_DUMP"], "w", encoding="utf-8") as f:
        json.dump({"argv": sys.argv[1:], "cwd": os.getcwd(), "env": keep}, f)
if env.get("FAKE_STREAM"):
    with open(env["FAKE_STREAM"], encoding="utf-8") as f:
        for line in f:
            sys.stdout.write(line)
            sys.stdout.flush()
if env.get("FAKE_STDERR"):
    sys.stderr.write(env["FAKE_STDERR"] + "\n")
if env.get("FAKE_SLEEP"):
    seconds = float(env["FAKE_SLEEP"])
    child = subprocess.Popen(["sleep", str(int(seconds) + 1)])
    if env.get("FAKE_CHILD"):
        with open(env["FAKE_CHILD"], "w", encoding="utf-8") as f:
            f.write(str(child.pid))
    time.sleep(seconds)
sys.exit(int(env.get("FAKE_EXIT", "0")))
