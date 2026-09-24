"""에이전트 CLI 대역: 스트림 파일을 재생하고 호출 내용을 기록한다.

환경 변수로 제어한다.
FAKE_STREAM  줄을 stdout에 쓸 파일
FAKE_DUMP    {"argv", "cwd", "env"}를 JSON으로 받을 파일
FAKE_SLEEP   스트림 뒤에 잠들 초(자식 ``sleep``도 함께 시작한다)
FAKE_CHILD   그 자식의 pid를 받을 파일
FAKE_STDERR  stderr에 쓸 텍스트
FAKE_EXIT    종료 코드
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
