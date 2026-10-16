#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Optional Antigravity CLI (agy) 1.3.5 worker with a truthful terminal verdict.

The adapter distinguishes the actual CLI process exit from the structured
terminal status in the native NDJSON stream, so a process exit 0 plus a
terminal ERROR result can never look like a successful completed agent
call. No fallback, no retry, no plugin/auth/billing manipulation.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

VERSION = "1.3.5"
# Fixed Gemini 3.8 Flash selectors advertised by the pinned CLI; the generic
# --effort flag is never passed for these variants and requested effort is
# derived from the selector name only.
SELECTORS = {"high": "gemini-3.8-flash-high",
             "medium": "gemini-3.8-flash-medium",
             "low": "gemini-3.8-flash-low"}
# agy has no prompt-file flag. Its help documents an NDJSON stdin input mode
# whose message schema is not established from help or owned logs, so no stdin
# format is guessed: the task travels as the single -p argv string. Linux caps
# one argv string at 131072 bytes (MAX_ARG_STRLEN); the adapter refuses tasks
# above half that bound before any provider call rather than truncating.
TASK_ARG_BYTES = 65536
OUTPUT_BYTES = 8388608
META_BYTES = 65536
TIME_LIMIT_MAX = 7200


class Refusal(Exception):
    pass


def date():
    return subprocess.check_output(["date", "-Is"], text=True, timeout=5).strip()


def read_regular(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise Refusal("invalid_or_oversized_file")
        data = source.read(limit + 1)
        if len(data) > limit:
            raise Refusal("invalid_or_oversized_file")
    data.decode("utf-8", errors="strict")
    if b"\0" in data:
        raise Refusal("invalid_utf8_task")
    return data


def read_raw(path, limit):
    """Bounded raw bytes; the native stream is decoded strictly by the parser."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise Refusal("invalid_or_oversized_file")
        data = source.read(limit + 1)
        if len(data) > limit:
            raise Refusal("invalid_or_oversized_file")
    return data


def read_task(path):
    """Bounded UTF-8 task; an oversized prompt is refused before any provider call."""
    try:
        info = os.stat(path, follow_symlinks=False)
    except OSError:
        raise Refusal("invalid_or_oversized_file") from None
    if not stat.S_ISREG(info.st_mode) or info.st_size > TASK_ARG_BYTES:
        if stat.S_ISREG(info.st_mode):
            raise Refusal("task_exceeds_argv_bound")
        raise Refusal("invalid_or_oversized_file")
    return read_regular(path, TASK_ARG_BYTES)


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("nonfinite JSON")
    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)


def private_file(path, data):
    with open(path, "xb") as out:
        os.chmod(path, 0o600)
        out.write(data)


def write_receipt(path, record):
    path.write_text(json.dumps(record, indent=2) + "\n")
    os.chmod(path, 0o600)


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1048576), b""):
            digest.update(block)
    return digest.hexdigest()


def exited(child):
    """Leader exit without reaping, so its process-group id cannot be reused yet."""
    try:
        return os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None
    except ChildProcessError:
        return True


def stop_group(child):
    # Signal only this invocation's own new process group, including descendants.
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(child.pid, sig)
        except ProcessLookupError:
            return
        if sig == signal.SIGTERM:
            time.sleep(.1)


def owned_call(argv, env, seconds, cwd=None, data=b"", sinks=(None, None), output_limit=OUTPUT_BYTES):
    """Bound owned process-group lifetime and combined output; feed data via stdin."""
    child = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             start_new_session=True, umask=0o077)
    poll = selectors.DefaultSelector()
    streams = {child.stdout: 0, child.stderr: 1}
    for pipe in streams:
        poll.register(pipe, selectors.EVENT_READ)
    if data:
        os.set_blocking(child.stdin.fileno(), False)
        poll.register(child.stdin, selectors.EVENT_WRITE)
    else:
        child.stdin.close()
    deadline = time.monotonic() + seconds
    view, sent, seen, stopped = memoryview(data), 0, 0, False
    capture = (bytearray(), bytearray())
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Refusal("timeout")
            if not stopped and exited(child):
                # Descendants must not outlive the native parent or hold its pipes.
                stop_group(child)
                stopped = True
            if not poll.get_map():
                if stopped:
                    break
                time.sleep(min(remaining, .05))
                continue
            for key, _ in poll.select(min(remaining, .2)):
                if key.fileobj is child.stdin:
                    try:
                        sent += os.write(child.stdin.fileno(), view[sent:sent + 65536])
                    except BrokenPipeError:
                        sent = len(data)
                    if sent >= len(data):
                        poll.unregister(child.stdin)
                        child.stdin.close()
                    continue
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    poll.unregister(key.fileobj)
                    continue
                seen += len(chunk)
                if seen > output_limit:
                    raise Refusal("output_limit")
                index = streams[key.fileobj]
                if sinks[index] is None:
                    capture[index].extend(chunk)
                else:
                    sinks[index].write(chunk)
        return child.wait(timeout=5), bytes(capture[0]), bytes(capture[1])
    finally:
        poll.close()
        if child.returncode is None:
            stop_group(child)
        for pipe in (child.stdin, child.stdout, child.stderr):
            pipe.close()
        child.wait(timeout=5)


def native_duration(seconds):
    """Go duration string; whole minutes match the proven `55m` form exactly."""
    seconds = int(math.ceil(seconds))
    if seconds % 60 == 0:
        return str(seconds // 60) + "m"
    return str(seconds) + "s"


def terminal_record(value):
    """Classify one top-level native stream record.

    Only the top-level event/result envelope counts. Text inside assistant or
    tool content never produces a terminal verdict, and any malformed shape
    invalidates the stream instead of inventing success. Returns None for a
    non-terminal record, or a (state, status) pair for a terminal candidate.
    """
    if not isinstance(value, dict) or not isinstance(value.get("event"), str):
        raise Refusal("invalid_stream_record")
    if value["event"] != "result":
        return None
    result = value.get("result")
    if not isinstance(result, dict):
        raise Refusal("invalid_terminal_result")
    status = result.get("status")
    if not isinstance(status, str) or not status:
        raise Refusal("invalid_terminal_status")
    error = result.get("error")
    if error is not None and not isinstance(error, str):
        raise Refusal("invalid_terminal_error_shape")
    response = result.get("response")
    if response is not None and not isinstance(response, str):
        raise Refusal("invalid_terminal_response_shape")
    return status, error


def parse_stream(raw):
    """Strict bounded NDJSON verdict; returns (state, status, error_present).

    state is "valid" only when every nonempty line is a distinct JSON object
    and exactly one terminal result record is present.
    """
    terminals = []
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError:
        return "invalid_stream_encoding", None, False
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            value = strict_json(line)
        except (ValueError, UnicodeError, RecursionError):
            return "invalid_stream_record", None, False
        try:
            classified = terminal_record(value)
        except Refusal as refusal:
            return str(refusal), None, False
        if classified is not None:
            terminals.append(classified)
    if not terminals:
        return "missing_terminal_result", None, False
    if len(terminals) != 1:
        return "ambiguous_terminal_result", None, False
    status, error = terminals[0]
    normalized_status = status if status in ("SUCCESS", "ERROR") else None
    return "valid", normalized_status, error is not None and error != ""


def main():
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selector", choices=tuple(SELECTORS), default="high",
                        help="Fixed Gemini 3.8 Flash variant; high is the default")
    parser.add_argument("--prompt-file", help="Regular UTF-8 task with all selected context inline; otherwise TASKFILE")
    parser.add_argument("--receipt-dir", required=True, help="Existing private parent; each invocation creates a new run")
    parser.add_argument("--time-limit", type=float, default=3300,
                        help="Native print-mode deadline in seconds, up to 7200")
    args = parser.parse_args()
    record = None
    receipt = None
    started = time.monotonic()
    exit_code = 2
    try:
        if not math.isfinite(args.time_limit) or not 0 < args.time_limit <= TIME_LIMIT_MAX:
            raise Refusal("invalid_bounds")
        prompt = args.prompt_file or os.environ.get("TASKFILE")
        if not prompt:
            raise Refusal("missing_task")
        # Refuse an oversized single-argument prompt before any provider call.
        data = read_task(prompt)
        parent = Path(args.receipt_dir).absolute()
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise Refusal("receipt_parent_must_be_private")
        cli = shutil.which("agy")
        if not cli:
            raise Refusal("missing_cli")
        cli = os.path.realpath(cli)
        # Quiet metadata preflight: version only, no provider call.
        code, version, _ = owned_call([cli, "--version"], None, 30, output_limit=4096)
        if code or version.decode("ascii", errors="replace").strip() != VERSION:
            raise Refusal("unsupported_cli")
        directory = Path(tempfile.mkdtemp(prefix="antigravity-run-", dir=parent))
        receipt = directory / "receipt.json"
        task = directory / "task.md"
        stdout_path = directory / "native-stdout.log"
        stderr_path = directory / "native-stderr.log"
        private_file(task, data)
        record = dict(schema_version=1, started_at=date(), role="implementation_worker",
                      transport="Antigravity CLI print mode", cli_version=VERSION,
                      cli_sha256=file_sha256(cli), task_sha256=hashlib.sha256(data).hexdigest(),
                      task_bytes=len(data), prompt_transport="argv_single_argument",
                      prompt_transport_bound_bytes=TASK_ARG_BYTES,
                      requested_model=SELECTORS[args.selector], requested_effort=args.selector,
                      effective_model="unknown", effective_ai_lab="unknown",
                      effective_effort="unknown", remaining_allowance="unknown",
                      budget_group="antigravity", subscription="owner_reported",
                      native_limits=dict(time_limit=args.time_limit,
                                         print_timeout=native_duration(args.time_limit),
                                         output_bytes=OUTPUT_BYTES),
                      trust=dict(parent_shell="trusted_host", native_credentials="trusted_host",
                                 sandbox=False, permission_mode="always_proceed_requested"),
                      invocations=0, invocation_retries=0, fallback_route="none",
                      native_exit=None, terminal_status=None, terminal_error=False,
                      outcome="preflight", task_path=str(task), stdout_path=str(stdout_path),
                      stderr_path=str(stderr_path))
        write_receipt(receipt, record)
        argv = [cli, "-p", data.decode("utf-8"), "--mode", "accept-edits",
                "--model", SELECTORS[args.selector],
                "--dangerously-skip-permissions", "--disable-slash-commands",
                "--print-timeout", native_duration(args.time_limit),
                "--output-format", "stream-json"]
        record["invocations"] = 1
        record["outcome"] = "starting"
        write_receipt(receipt, record)
        with open(stdout_path, "xb") as out, open(stderr_path, "xb") as err:
            os.chmod(stdout_path, 0o600)
            os.chmod(stderr_path, 0o600)
            code, _, _ = owned_call(argv, None, args.time_limit + min(60.0, max(5.0, args.time_limit * .02)),
                                    Path.cwd(), sinks=(out, err))
        record["native_exit"] = code
        if code < 0:
            # Signal death has no exit code; report it truthfully as 128+signal.
            record["outcome"] = "native_signal"
            exit_code = 128 - code if 0 < -code <= 127 else 2
        elif code:
            # Preserve the real native exit regardless of missing terminal data.
            record["outcome"] = "native_failed"
            exit_code = code
        else:
            state, status, error_present = parse_stream(read_raw(stdout_path, OUTPUT_BYTES))
            record["terminal_status"] = status
            record["terminal_error"] = error_present
            if state != "valid":
                record["outcome"] = state
                exit_code = 2
            elif status != "SUCCESS":
                # A response body alongside ERROR never repairs the verdict.
                record["outcome"] = "terminal_error" if status == "ERROR" else "unknown_terminal_status"
                exit_code = 2
            elif error_present:
                record["outcome"] = "success_with_error"
                exit_code = 2
            else:
                record["outcome"] = "terminal_success"
                exit_code = 0
    except KeyboardInterrupt:
        exit_code = 130
        if record is not None:
            record["outcome"] = "interrupted"
    except (Refusal, OSError, ValueError, UnicodeError, subprocess.SubprocessError) as error:
        state = str(error) if isinstance(error, Refusal) else "local_failure"
        if record is not None:
            record["outcome"] = state
        print("Antigravity adapter: " + state, file=sys.stderr)
        exit_code = 124 if state == "timeout" else 2
    finally:
        if record is not None:
            record.update(adapter_exit=exit_code, elapsed_seconds=round(time.monotonic() - started, 3), finished_at=date())
            write_receipt(receipt, record)
            if os.environ.get("UNIO_ADAPTER_OUTCOME"):
                try:
                    import runpy
                    runpy.run_path(str(Path(__file__).with_name("adapter-outcome.py")))["emit"](
                        "antigravity", record, prompt, exit_code, record.get("native_exit"))
                except Exception:
                    pass  # Optional evidence must never replace the real exit.
            print(json.dumps({"receipt": str(receipt), "adapter_exit": exit_code,
                              "native_exit": record["native_exit"], "outcome": record["outcome"],
                              "terminal_status": record["terminal_status"],
                              "terminal_error": record["terminal_error"]}))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
