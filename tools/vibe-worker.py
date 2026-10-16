#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Optional, explicitly pinned Vibe 2.26.1 worker. No dependency installation."""
import argparse
import codecs
from datetime import datetime, timezone
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

VERSION = "2.26.1"
MODELS = {
    "glm-5-3": ("zai-glm-5-3", "Z.ai", 1.4, .14, 4.4),
    "mistral-medium-3-5": ("mistral-medium-3-5", "Mistral", 1.5, .15, 7.5),
}
PROMPT_BYTES = 1048576
OUTPUT_BYTES = 16777216
EXPORT_BYTES = 8388608
# Public progress bounds: one NDJSON record and total printed lines are capped so
# a noisy or hostile stream can neither grow memory nor spam the public log.
HEARTBEAT_SECONDS = 30.0
PROGRESS_RECORD_BYTES = 262144
PROGRESS_LINES = 10000
PROGRESS_PREFIX = "Vibe progress: "
HEARTBEAT_PREFIX = "Vibe heartbeat: "
HEARTBEAT_LABEL = "adapter process alive; no new provider event observed"
# Fixed operational labels only. Nothing from a stream record is ever printed.
EFFECT_LABELS = {
    "shell": "running shell command",
    "file_read": "reading file",
    "file_edit": "editing file",
    "file_write": "writing file",
    "file_search": "searching files",
    "todo": "updating task list",
}


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


class Progress:
    """Bounded fixed-label public progress from the CLI's NDJSON stream.

    The provider invocation uses the installed CLI's documented --output
    streaming route: one JSON record per completed session history entry.
    Raw bytes still go to the private native stdout log; this class only
    ever prints allowlisted operational labels, never record content,
    prompts, answers, reasoning, tool arguments/results, paths, commands,
    exports, authentication or error text. Unknown events are counted,
    not invented progress. The heartbeat reports adapter process liveness
    only and is distinct from an observed provider/tool event.
    """

    def __init__(self, stream=None):
        self.stream = sys.stdout if stream is None else stream
        self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.buffer = ""
        self.discard = False
        self.events = 0
        self.heartbeats = 0
        self.malformed = 0
        self.unlabeled = 0
        self.printed = 0
        self.last_label = None
        self.last_observed_at = None
        self.last_emit = time.monotonic()

    def silent_for(self):
        return time.monotonic() - self.last_emit

    def heartbeat(self):
        self.heartbeats += 1
        self.last_emit = time.monotonic()
        self._print(HEARTBEAT_PREFIX + HEARTBEAT_LABEL)

    def feed(self, chunk):
        text = self.decoder.decode(chunk)
        if self.discard:
            end = text.find("\n")
            if end < 0:
                return
            self.discard = False
            text = text[end + 1:]
        self.buffer += text
        while True:
            end = self.buffer.find("\n")
            if end < 0:
                if len(self.buffer) > PROGRESS_RECORD_BYTES:
                    self.malformed += 1
                    self.buffer = ""
                    self.discard = True
                return
            line = self.buffer[:end]
            self.buffer = self.buffer[end + 1:]
            if len(line) > PROGRESS_RECORD_BYTES:
                self.malformed += 1
                continue
            self.record(line)

    def record(self, line):
        line = line.strip()
        if not line:
            return
        try:
            value = json.loads(line)
        except (ValueError, RecursionError):
            self.malformed += 1
            return
        label = self.label(value)
        if label is None:
            self.unlabeled += 1
            return
        self.events += 1
        self.last_label = label
        self.last_observed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.last_emit = time.monotonic()
        self._print(PROGRESS_PREFIX + label)

    def label(self, value):
        if not isinstance(value, dict):
            return None
        kind = value.get("type")
        if not isinstance(kind, str):
            return None
        if kind == "message":
            return "assistant response observed" if value.get("role") == "assistant" else None
        if kind == "reasoning":
            return "assistant reasoning observed"
        if kind == "effect":
            detail = value.get("detail")
            state = value.get("state")
            if not isinstance(detail, dict) or not isinstance(state, dict):
                return None
            status = state.get("status")
            effect_kind = detail.get("kind")
            if not isinstance(status, str) or not isinstance(effect_kind, str):
                return None
            if status == "failed":
                return "tool failure observed"
            return EFFECT_LABELS.get(effect_kind, "tool call observed")
        return None

    def _print(self, line):
        if self.printed >= PROGRESS_LINES:
            return
        self.printed += 1
        print(line, file=self.stream, flush=True)

    def summary(self):
        return dict(events=self.events, heartbeats=self.heartbeats,
                    malformed_records=self.malformed, unlabeled_records=self.unlabeled,
                    last_label=self.last_label, last_observed_at=self.last_observed_at)


def model_environment(label, inherited=None):
    wire, lab, inp, cache, out = MODELS[label]
    model = dict(name=wire, alias=label, provider="mistral", thinking="high",
                 thinking_levels=["high"], input_price=inp,
                 cached_input_price=cache, output_price=out)
    env = {k: v for k, v in (os.environ if inherited is None else inherited).items()
           if not k.startswith("VIBE_") or k == "VIBE_HOME"}
    env.update(VIBE_ACTIVE_MODEL=label, VIBE_MODELS=json.dumps({label: model}),
               VIBE_ALLOWED_MODELS=json.dumps([wire]), VIBE_COMPACTION_MODEL=json.dumps(model),
               VIBE_UTILITY_MODELS=json.dumps({"title": "active", "smart_approve": "active"}),
               VIBE_SESSION_LOGGING__GENERATE_TITLES="false", VIBE_ENABLE_UPDATE_CHECKS="false",
               VIBE_ENABLE_AUTO_UPDATE="false", VIBE_EXPERIMENTS__ENABLE="false",
               VIBE_MCP_SERVERS="[]", VIBE_ENABLE_SUBAGENTS="false", VIBE_ENABLE_CONNECTORS="false",
               VIBE_API_RETRY_MAX_ELAPSED_TIME="0", PYTHONDONTWRITEBYTECODE="1")
    return env, wire, lab


def owned_call(argv, env, seconds, log=None, output_limit=OUTPUT_BYTES, progress=None):
    """Bound owned process-group lifetime and output, including preflight output."""
    child = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    poll = selectors.DefaultSelector()
    poll.register(child.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + seconds
    seen = 0
    capture = bytearray()
    try:
        while poll.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Refusal("timeout")
            if progress is not None and progress.silent_for() >= HEARTBEAT_SECONDS:
                progress.heartbeat()
            for key, _ in poll.select(min(remaining, .2)):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    poll.unregister(key.fileobj)
                    continue
                seen += len(chunk)
                if seen > output_limit:
                    raise Refusal("output_limit")
                if log is None:
                    capture.extend(chunk)
                else:
                    log.write(chunk)
                if progress is not None:
                    progress.feed(chunk)
        while child.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Refusal("timeout")
            if progress is not None and progress.silent_for() >= HEARTBEAT_SECONDS:
                progress.heartbeat()
            try:
                child.wait(timeout=min(max(.001, remaining), .2))
            except subprocess.TimeoutExpired:
                pass
        return child.returncode, bytes(capture)
    finally:
        poll.close()
        child.stdout.close()
        # Reap only this invocation's own new process group, including descendants.
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(child.pid, sig)
            except ProcessLookupError:
                break
            if sig == signal.SIGTERM:
                time.sleep(.1)
        child.wait(timeout=5)


def export_summary(path, actual_exit):
    value = strict_json(read_regular(path, EXPORT_BYTES))
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise Refusal("invalid_export")
    if value.get("vibe_version") != VERSION or type(value.get("exit_code")) is not int or value["exit_code"] != actual_exit:
        raise Refusal("invalid_export")
    outcomes = {"finished": 0, "usage_error": 1, "config_error": 1,
                "infrastructure_failure": 2, "token_limit": 3, "price_limit": 3,
                "turn_limit": 3, "deadline": 3, "terminated": 3,
                "length": 3, "refusal": 3, "aborted": 4}
    if not isinstance(value.get("outcome"), str) or value["outcome"] not in outcomes or outcomes[value["outcome"]] != actual_exit:
        raise Refusal("invalid_export")
    stop = value.get("stop_reason")
    if stop not in (None, "interrupted", "limit", "length"):
        raise Refusal("invalid_export")
    usage = value.get("usage")
    if usage is not None and not isinstance(usage, dict):
        raise Refusal("invalid_export")
    fields = ("input_tokens", "output_tokens", "cached_input_tokens", "total_tokens")
    if usage is not None and any(type(usage.get(k)) is not int or not 0 <= usage[k] <= 10**12 for k in fields):
        raise Refusal("invalid_export")
    if usage is not None and (usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"] or usage["cached_input_tokens"] > usage["input_tokens"]):
        raise Refusal("invalid_export")
    cost = value.get("cost_usd")
    if cost is not None and (type(cost) not in (int, float) or not 0 <= cost <= 10**6 or not math.isfinite(cost)):
        raise Refusal("invalid_export")
    return dict(schema_version=1, outcome=value["outcome"], stop_reason=stop,
                usage={k: usage[k] for k in fields} if usage is not None else None,
                estimated_cost_usd=cost)


def main():
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, choices=MODELS)
    parser.add_argument("--prompt-file", help="Regular UTF-8 task; otherwise TASKFILE")
    parser.add_argument("--receipt-dir", required=True, help="Existing private parent; each invocation creates a new run")
    parser.add_argument("--max-price", type=float, default=5.0)
    parser.add_argument("--max-tokens", type=int, default=2000000)
    parser.add_argument("--time-limit", type=float, default=5400)
    parser.add_argument("--max-turns", type=int, default=120)
    args = parser.parse_args()
    record = None
    receipt = None
    progress = None
    started = time.monotonic()
    exit_code = 2
    try:
        if not math.isfinite(args.max_price) or not 0 < args.max_price <= 10:
            raise Refusal("invalid_bounds")
        if not 0 < args.max_tokens <= 4000000 or not 0 < args.max_turns <= 180:
            raise Refusal("invalid_bounds")
        if not math.isfinite(args.time_limit) or not 0 < args.time_limit <= 7200:
            raise Refusal("invalid_bounds")
        prompt = args.prompt_file or os.environ.get("TASKFILE")
        if not prompt:
            raise Refusal("missing_task")
        data = read_regular(prompt, PROMPT_BYTES)
        parent = Path(args.receipt_dir).absolute()
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise Refusal("receipt_parent_must_be_private")
        cli = shutil.which("vibe")
        if not cli:
            raise Refusal("missing_cli")
        env, wire, lab = model_environment(args.model)
        code, version = owned_call([cli, "--version"], env, 15, output_limit=4096)
        if code or version.decode("ascii").strip() != "vibe " + VERSION:
            raise Refusal("unsupported_cli")
        directory = Path(tempfile.mkdtemp(prefix="vibe-run-", dir=parent))
        receipt = directory / "receipt.json"
        task = directory / "task.md"
        with task.open("xb") as out:
            os.chmod(task, 0o600)
            out.write(data)
        export = directory / "native"
        export.mkdir(mode=0o700)
        record = dict(schema_version=1, started_at=date(), cli_version=VERSION,
                      requested_model=args.model, configured_wire_model=wire, ai_lab=lab,
                      transport="Mistral Vibe", budget_group="mistral", requested_effort="high",
                      configured_wire_effort="high", effective_model="unknown", effective_effort="unknown",
                      remaining_allowance="unknown", task_sha256=hashlib.sha256(data).hexdigest(),
                      native_limits=dict(max_price=args.max_price, max_tokens=args.max_tokens,
                                         time_limit=args.time_limit, max_turns=args.max_turns),
                      invocations=1, invocation_retries=0, process_exit=None, outcome="starting")
        receipt.write_text(json.dumps(record, indent=2) + "\n")
        argv = [cli, "--prompt-file", str(task), "--workdir", str(Path.cwd()), "--trust",
                "--agent", "auto-approve", "--max-price", str(args.max_price),
                "--max-tokens", str(args.max_tokens), "--time-limit", str(args.time_limit),
                "--max-turns", str(args.max_turns), "--output-dir", str(export),
                "--output", "streaming"]
        for name in ("bash", "read_file", "write_file", "edit", "grep"):
            argv.extend(["--enabled-tools", name])
        progress = Progress()
        with (directory / "native-stdout.log").open("xb") as log:
            code, _ = owned_call(argv, env, args.time_limit + 20, log, progress=progress)
        record["process_exit"] = code
        record["outcome"] = "process_finished"
        exit_code = code if code in (0, 1, 2, 3, 4) else 2
        try:
            record["export"] = export_summary(export / "export.json", code)
            if code == 0 and record["export"]["outcome"] != "finished":
                raise Refusal("inconsistent_export")
            record["export_state"] = "valid"
        except (OSError, ValueError, UnicodeError, Refusal, TypeError, OverflowError, RecursionError):
            record["export_state"] = "invalid_or_missing"
            if code == 0:
                exit_code = 2
    except KeyboardInterrupt:
        exit_code = 130
        if record is not None:
            record["outcome"] = "interrupted"
    except (Refusal, OSError, ValueError, UnicodeError, subprocess.SubprocessError) as error:
        state = str(error) if isinstance(error, Refusal) else "local_failure"
        if record is not None:
            record["outcome"] = state
        print("Vibe adapter: " + state, file=sys.stderr)
        exit_code = 124 if state == "timeout" else 2
    finally:
        if record is not None:
            if progress is not None:
                record["progress"] = progress.summary()
            record.update(adapter_exit=exit_code, elapsed_seconds=round(time.monotonic() - started, 3), finished_at=date())
            receipt.write_text(json.dumps(record, indent=2) + "\n")
            if os.environ.get("UNIO_ADAPTER_OUTCOME"):
                try:
                    import runpy
                    runpy.run_path(str(Path(__file__).with_name("adapter-outcome.py")))["emit"](
                        "vibe", record, prompt, exit_code, record.get("process_exit"))
                except Exception:
                    pass  # Optional evidence must never replace the real exit.
            final = {"receipt": str(receipt), "adapter_exit": exit_code,
                     "process_exit": record["process_exit"], "export_state": record.get("export_state", "unknown")}
            if progress is not None:
                final.update(progress_events=progress.events, progress_last_label=progress.last_label)
            print(json.dumps(final))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
