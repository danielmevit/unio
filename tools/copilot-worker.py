#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Optional GitHub Copilot CLI 1.0.95 Balanced (Auto) routine-proposal worker.

Text proposals only: no model tools, patch execution or retry. Delivery is the
installed CLI's JSONL transport, not rendered text. The parent shell and the
native credential store stay trusted_host; this is not a sandbox.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

VERSION = "1.0.95"
PROMPT_BYTES = 1048576
OUTPUT_BYTES = 8388608
META_BYTES = 1048576
KEEP_ENV = ("COPILOT_HOME", "COPILOT_GITHUB_TOKEN")
MCP_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
UUID = re.compile(r"\A[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z")
INVALID = "empty_or_invalid_response"
# Installed Copilot CLI 1.0.95 --help: --output-format json is JSONL.
# Package @github/copilot 1.0.95 (build f5ba5057) cli-main.js Han writes
# JSON.stringify(sessionEvent)+"\n", skipping IM() model-log events and the
# qZr set (session.idle, assistant.streaming_delta, assistant.usage, permission.*,
# system.message, skill.*, and the other listed UI/session events). Prompt mode
# then appends Gan's terminal result: type, timestamp, sessionId, exitCode, usage
# {premiumRequests, totalApiDurationMs, sessionDurationMs, codeChanges{linesAdded,
# linesRemoved, filesModified}}. assistant.message data.content is the full root
# text (session-events schema). Deltas, tool output, user echoes and subagents
# are not that completion. No second render or JSON repair.
MAX_JSON_DEPTH = 64
MAX_JSON_EVENTS = 10000
MAX_JSON_NODES = 200000
ID_LIMIT = 512
ASSISTANT_EVENT_KEYS = {"id", "timestamp", "parentId", "ephemeral", "agentId", "type", "data"}
ASSISTANT_DATA_KEYS = {
    "messageId", "originatingMessageId", "model", "providerId", "content", "toolRequests",
    "reasoningOpaque", "reasoningText", "reasoningWireField", "encryptedContent", "phase",
    "chunkIndex", "chunkCount", "outputTokens", "interactionId", "requestId", "clientRequestId",
    "serviceRequestId", "rte", "apiCallId", "serverTools", "reasoningBlocks", "turnId",
    "parentToolCallId", "citations", "fusion",
}
GROUP_KEYS = ("turnId", "originatingMessageId")
RESULT_KEYS = {"type", "timestamp", "sessionId", "exitCode", "usage"}
USAGE_KEYS = {"premiumRequests", "totalApiDurationMs", "sessionDurationMs", "codeChanges"}
CHANGE_KEYS = {"linesAdded", "linesRemoved", "filesModified"}
# The proposal role needs no model tool; view is the smallest non-empty allowlist.
AVAILABLE = ("view",)
EXCLUDED = ("task", "list_agents", "read_agent", "write_agent", "skill", "ask_user")
DENIED = ("read", "write", "shell", "url", "memory")


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


def bounded_json(value):
    """Reject nonfinite numbers and unbounded nesting without rewriting strings."""
    stack, nodes = [(value, 0)], 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if depth > MAX_JSON_DEPTH or nodes > MAX_JSON_NODES:
            raise Refusal(INVALID)
        if isinstance(item, float):
            if not math.isfinite(item):
                raise Refusal(INVALID)
        elif isinstance(item, dict):
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
        elif not isinstance(item, (str, int, bool)) and item is not None:
            raise Refusal(INVALID)


def identifier(value):
    return isinstance(value, str) and 0 < len(value) <= ID_LIMIT


def whole_number(value):
    return isinstance(value, int) and not isinstance(value, bool)


def finite_number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def subagent(event):
    """Same root test as the CLI's Ra(): agentId or a non-empty parentToolCallId."""
    agent = event.get("agentId")
    if isinstance(agent, str) and agent:
        return True
    data = event.get("data")
    if not isinstance(data, dict):
        return False
    for key in ("agentId", "parentToolCallId"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return True
    return False


def parse_jsonl(raw):
    if (not raw or raw.startswith(b"\xef\xbb\xbf") or b"\0" in raw or b"\r" in raw
            or raw[:1] in (b" ", b"\t", b"\n") or not raw.endswith(b"\n")):
        raise Refusal(INVALID)
    try:
        text = raw.decode("utf-8")
    except UnicodeError as error:
        raise Refusal(INVALID) from error
    lines = text[:-1].split("\n")
    if not lines or len(lines) > MAX_JSON_EVENTS:
        raise Refusal(INVALID)
    events = []
    for line in lines:
        if not line or line[0] != "{" or line[-1] != "}":
            raise Refusal(INVALID)
        try:
            event = strict_json(line)
        except (ValueError, UnicodeError, RecursionError) as error:
            raise Refusal(INVALID) from error
        bounded_json(event)
        if not isinstance(event, dict) or not isinstance(event.get("type"), str) or not event["type"]:
            raise Refusal(INVALID)
        events.append(event)
    return events


def require_assistant(event):
    if set(event) - ASSISTANT_EVENT_KEYS or not {"id", "timestamp", "parentId", "type", "data"} <= set(event):
        raise Refusal(INVALID)
    if event["type"] != "assistant.message" or not isinstance(event["id"], str) or not UUID.fullmatch(event["id"]):
        raise Refusal(INVALID)
    if not identifier(event["timestamp"]):
        raise Refusal(INVALID)
    parent = event["parentId"]
    if parent is not None and not identifier(parent):
        raise Refusal(INVALID)
    if "ephemeral" in event and not isinstance(event["ephemeral"], bool):
        raise Refusal(INVALID)
    if "agentId" in event and not identifier(event["agentId"]):
        raise Refusal(INVALID)
    data = event["data"]
    if not isinstance(data, dict) or set(data) - ASSISTANT_DATA_KEYS or not {"messageId", "content"} <= set(data):
        raise Refusal(INVALID)
    if not identifier(data["messageId"]) or not isinstance(data["content"], str):
        raise Refusal(INVALID)
    for key in GROUP_KEYS:
        if key in data and not identifier(data[key]):
            raise Refusal(INVALID)
    if "toolRequests" in data and not isinstance(data["toolRequests"], list):
        raise Refusal(INVALID)
    has_index, has_count = "chunkIndex" in data, "chunkCount" in data
    if has_index != has_count:
        raise Refusal(INVALID)
    if has_index:
        index, count = data["chunkIndex"], data["chunkCount"]
        if not whole_number(index) or not whole_number(count) or count < 1 or index < 0 or index >= count:
            raise Refusal(INVALID)
    return event


def require_result(event):
    if set(event) != RESULT_KEYS or event["type"] != "result":
        raise Refusal(INVALID)
    if not identifier(event["timestamp"]) or not identifier(event["sessionId"]):
        raise Refusal(INVALID)
    if not whole_number(event["exitCode"]) or event["exitCode"] not in (0, 1):
        raise Refusal(INVALID)
    usage = event["usage"]
    if not isinstance(usage, dict) or set(usage) != USAGE_KEYS:
        raise Refusal(INVALID)
    for key in ("premiumRequests", "totalApiDurationMs", "sessionDurationMs"):
        if not finite_number(usage[key]):
            raise Refusal(INVALID)
    changes = usage["codeChanges"]
    if not isinstance(changes, dict) or set(changes) != CHANGE_KEYS:
        raise Refusal(INVALID)
    for key in ("linesAdded", "linesRemoved"):
        val = changes[key]
        if not whole_number(val) or val < 0 or not finite_number(val):
            raise Refusal(INVALID)
    files = changes["filesModified"]
    valid_files = (
        (whole_number(files) and files >= 0 and finite_number(files))
        or (isinstance(files, list) and all(identifier(item) for item in files))
    )
    if not valid_files:
        raise Refusal(INVALID)
    if event["exitCode"] != 0:
        raise Refusal(INVALID)
    return event


def completion_text(messages):
    if not messages:
        raise Refusal(INVALID)
    if len({event["data"]["messageId"] for event in messages}) != len(messages):
        raise Refusal(INVALID)
    chunked = [event for event in messages if "chunkIndex" in event["data"]]
    if chunked and len(chunked) != len(messages):
        raise Refusal(INVALID)
    if chunked and any(event["data"].get("toolRequests") for event in messages):
        raise Refusal(INVALID)
    if chunked:
        count = messages[0]["data"]["chunkCount"]
        if any(event["data"]["chunkCount"] != count for event in messages) or len(messages) != count:
            raise Refusal(INVALID)
        for key in GROUP_KEYS:
            values = set()
            for event in messages:
                if key in event["data"]:
                    val = event["data"][key]
                    if not identifier(val):
                        raise Refusal(INVALID)
                    values.add(val)
            if len(values) > 1:
                raise Refusal(INVALID)
        ordered = sorted(messages, key=lambda event: event["data"]["chunkIndex"])
        if [event["data"]["chunkIndex"] for event in ordered] != list(range(count)):
            raise Refusal(INVALID)
        return "".join(event["data"]["content"] for event in ordered)
    plain = [event for event in messages
             if not event["data"].get("toolRequests") and event["data"]["content"].strip()]
    if len(plain) != 1:
        raise Refusal(INVALID)
    return plain[0]["data"]["content"]


def proposal_from_jsonl(raw):
    """Exact root assistant text, or Refusal. Bytes are not repaired or rewrapped."""
    events = parse_jsonl(raw)
    results = [event for event in events if event["type"] == "result"]
    if len(results) != 1 or events[-1] is not results[0]:
        raise Refusal(INVALID)
    require_result(results[0])
    seen, messages = set(), []
    for event in events[:-1]:
        if event["type"] == "assistant.message":
            require_assistant(event)
            if not subagent(event):
                messages.append(event)
        elif event["type"] == "result":
            raise Refusal(INVALID)
        identity = event.get("id")
        if "id" in event:
            if not identifier(identity) or identity in seen:
                raise Refusal(INVALID)
            seen.add(identity)
    text = completion_text(messages)
    try:
        text.encode("utf-8")
    except UnicodeError as error:
        raise Refusal(INVALID) from error
    if not text.strip() or "\0" in text:
        raise Refusal(INVALID)
    return text


def route_environment(providers, inherited=None):
    """Native auth and home only; no inherited Copilot, provider or Git routing."""
    env = {k: v for k, v in (os.environ if inherited is None else inherited).items()
           if not (k.startswith("COPILOT_") or k.startswith("GIT_")) or k in KEEP_ENV}
    env["COPILOT_PROVIDERS_CONFIG"] = str(providers)
    return env


def private_file(path, data):
    with open(path, "xb") as out:
        os.chmod(path, 0o600)
        out.write(data)


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


def metadata(cli, env, cwd, *command):
    return owned_call([cli, "--no-auto-update", *command], env, 60, cwd, output_limit=META_BYTES)


def auto_fallback_setting(cli, env, cwd):
    code, out, err = metadata(cli, env, cwd, "config", "continueOnAutoMode")
    value = out.decode("utf-8", errors="replace").strip()
    if code == 1 and not value and not err.strip():
        return "unset"
    if code == 0 and value == "false":
        return "false"
    raise Refusal("auto_fallback_enabled" if code == 0 and value == "true" else "unrecognized_auto_fallback_setting")


def refuse_plugins(cli, env, cwd):
    code, out, _ = metadata(cli, env, cwd, "plugin", "list", "--json")
    try:
        plugins = strict_json(out) if code == 0 else None
    except (ValueError, UnicodeError, RecursionError):
        plugins = None
    if not isinstance(plugins, list):
        raise Refusal("invalid_plugin_metadata")
    if plugins:
        raise Refusal("plugins_present")


def refuse_extensions(env):
    home = Path(env["COPILOT_HOME"]) if env.get("COPILOT_HOME") else Path.home() / ".copilot"
    path = home / "extensions"
    if os.path.lexists(path) and (path.is_symlink() or not path.is_dir() or any(path.iterdir())):
        raise Refusal("extensions_present")


def mcp_names(cli, env, cwd):
    """Server names only; raw MCP configuration and headers are never kept."""
    code, out, _ = metadata(cli, env, cwd, "mcp", "list", "--json")
    try:
        value = strict_json(out) if code == 0 else None
    except (ValueError, UnicodeError, RecursionError):
        value = None
    servers = value.get("mcpServers", {}) if isinstance(value, dict) else None
    if not isinstance(servers, dict) or len(servers) > 64:
        raise Refusal("invalid_mcp_metadata")
    if not all(isinstance(name, str) and MCP_NAME.fullmatch(name) for name in servers):
        raise Refusal("invalid_mcp_metadata")
    return sorted(servers)


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1048576), b""):
            digest.update(block)
    return digest.hexdigest()


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt-file", help="Regular UTF-8 task with all selected context inline; otherwise TASKFILE")
    parser.add_argument("--receipt-dir", required=True, help="Existing private parent; each invocation creates a new run")
    parser.add_argument("--time-limit", type=float, default=900)
    parser.add_argument("--max-ai-credits", type=int, default=30, help="Native soft cap, 30..300")
    return parser


def check_bounds(args):
    """Shared bound validator: the run and the route contract check agree."""
    problems = []
    if not math.isfinite(args.time_limit) or not 0 < args.time_limit <= 7200:
        problems.append("--time-limit " + str(args.time_limit)
                        + " is outside the supported bound (0, 7200] seconds; edit the agents.conf route and retry")
    if not 30 <= args.max_ai_credits <= 300:
        problems.append("--max-ai-credits " + str(args.max_ai_credits)
                        + " is outside the supported bound 30..300 credits")
    return problems


def budget_module():
    """Load the shared telemetry module installed beside this adapter."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "unio_adapter_budget", str(Path(__file__).with_name("adapter-budget.py")))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def run_telemetry(record, native_usage):
    """Premium requests are real native data; tokens and USD stay unknown."""
    module = budget_module()
    if module is None:
        return None
    notes = ["the native CLI reports premium requests and durations, not tokens or USD; "
             "token and USD usage are unknown, not zero"]
    premium = native_usage.get("premiumRequests") if isinstance(native_usage, dict) else None
    if (isinstance(premium, (int, float)) and not isinstance(premium, bool)
            and math.isfinite(premium) and premium >= 0):
        notes.append("the native usage file reported " + str(premium)
                     + " premium request(s); this is not a token or USD measurement")
    completed = record.get("outcome") == "proposal_recorded"
    if completed:
        notes.append("turns count the single root assistant completion required by the proposal protocol")
    return module.telemetry(
        tokens=module.meter(None, None, "unknown"),
        turns=module.meter(1, None, "estimated") if completed else module.meter(None, None, "unknown"),
        usd=module.meter(None, None, "unknown"), notes=notes)


def contract_validate(argv):
    """Route-contract metadata mode: the real parser and bounds, no run."""
    import io
    parser = build_parser()
    captured = io.StringIO()
    original = sys.stderr
    try:
        sys.stderr = captured
        args = parser.parse_args(argv)
    except SystemExit:
        return dict(schema_version=1, adapter="copilot-worker", state="invalid",
                    detail=(captured.getvalue() or "unrecognized arguments").strip()[-400:])
    finally:
        sys.stderr = original
    problems = check_bounds(args)
    return dict(schema_version=1, adapter="copilot-worker",
                state="valid" if not problems else "invalid",
                detail="; ".join(problems) if problems else None)


def main():
    if sys.argv[1:2] == ["--contract-validate"]:
        print(json.dumps(contract_validate(sys.argv[2:])))
        return 0
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    args = build_parser().parse_args()
    record = None
    receipt = None
    native_usage = None
    started = time.monotonic()
    exit_code = 2
    try:
        if check_bounds(args):
            raise Refusal("invalid_bounds")
        prompt = args.prompt_file or os.environ.get("TASKFILE")
        if not prompt:
            raise Refusal("missing_task")
        data = read_regular(prompt, PROMPT_BYTES)
        parent = Path(args.receipt_dir).absolute()
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise Refusal("receipt_parent_must_be_private")
        cli = shutil.which("copilot")
        git = shutil.which("git")
        if not cli or not git:
            raise Refusal("missing_cli")
        cli = os.path.realpath(cli)
        env = route_environment(parent / "unused-providers.json")
        code, version, _ = owned_call([cli, "--no-auto-update", "--version"], env, 30, parent, output_limit=4096)
        lines = version.decode("utf-8", errors="replace").strip().splitlines()
        # Later lines may announce an update; only the first identifies the binary.
        if code or not lines or lines[0].strip() not in {"GitHub Copilot CLI " + VERSION, "GitHub Copilot CLI " + VERSION + "."}:
            raise Refusal("unsupported_cli")
        directory = Path(tempfile.mkdtemp(prefix="copilot-run-", dir=parent))
        receipt = directory / "receipt.json"
        proposal = directory / "proposal.md"
        raw_stdout = directory / "native-stdout.jsonl"
        usage = directory / "usage.json"
        stderr_path = directory / "native-stderr.log"
        record = dict(schema_version=1, started_at=date(), role="routine_proposal",
                      transport="GitHub Copilot CLI", cli_version=VERSION, cli_sha256=file_sha256(cli),
                      task_sha256=hashlib.sha256(data).hexdigest(), task_bytes=len(data), prompt_transport="stdin",
                      output_transport="copilot_jsonl_1.0.95",
                      budget_group="copilot", subscription="owner_reported_free", remaining_allowance="unknown",
                      requested_route=dict(name="Balanced", model="auto", auto_tier="balance"),
                      requested_effort="not_configurable_auto", effective_model="unknown", effective_ai_lab="unknown",
                      effective_effort="unknown",
                      native_limits=dict(max_ai_credits=args.max_ai_credits, max_ai_credits_kind="soft_post_response",
                                         time_limit=args.time_limit),
                      trust=dict(parent_shell="trusted_host", native_credentials="trusted_host", sandbox=False),
                      invocations=0, invocation_retries=0, fallback_route="none", native_exit=None,
                      outcome="preflight", proposal_path=str(proposal), raw_stdout_path=str(raw_stdout),
                      usage_path=str(usage), stderr_path=str(stderr_path))
        receipt.write_text(json.dumps(record, indent=2) + "\n")
        work = directory / "work"
        template = directory / "git-template"
        work.mkdir(mode=0o700)
        template.mkdir(mode=0o700)
        settings = work / ".github" / "copilot"
        settings.mkdir(parents=True)
        private_file(settings / "settings.json", b'{"disableAllHooks": true}\n')
        providers = directory / "providers.json"
        private_file(providers, b'{"providers": [], "models": []}\n')
        env = route_environment(providers)
        # A neutral repository bounds native parent-repository discovery.
        code, _, _ = owned_call([git, "init", "--quiet", "--template=" + str(template), str(work)],
                                env, 30, directory, output_limit=65536)
        if code:
            raise Refusal("git_init_failed")
        record["continue_on_auto_mode"] = auto_fallback_setting(cli, env, work)
        refuse_plugins(cli, env, work)
        refuse_extensions(env)
        names = mcp_names(cli, env, work)
        record.update(plugins=0, extensions="none", disabled_mcp_servers=names, builtin_mcps="disabled",
                      model_tools=dict(available=list(AVAILABLE), excluded=list(EXCLUDED), denied=list(DENIED)))
        argv = [cli, "--no-auto-update", "--model", "auto", "--auto-tier", "balance",
                "--max-ai-credits", str(args.max_ai_credits), "--usage-output-file", str(usage),
                "--log-dir", str(directory / "native-logs"), "--log-level", "none",
                "--stream", "off", "--output-format", "json", "--silent",
                "--no-custom-instructions", "--no-ask-user", "--no-experimental", "--no-bash-env",
                "--no-remote", "--no-remote-export", "--disable-builtin-mcps",
                "--secret-env-vars=" + ",".join(KEEP_ENV + ("GH_TOKEN", "GITHUB_TOKEN"))]
        for name in names:
            argv.append("--disable-mcp-server=" + name)
        argv.extend("--available-tools=" + name for name in AVAILABLE)
        argv.extend("--excluded-tools=" + name for name in EXCLUDED)
        argv.extend("--deny-tool=" + name for name in DENIED)
        # Required for non-interactive mode; deny rules still take precedence.
        argv.append("--allow-all-tools")
        record.update(invocations=1, outcome="starting")
        receipt.write_text(json.dumps(record, indent=2) + "\n")
        with open(raw_stdout, "xb") as out, open(stderr_path, "xb") as err:
            os.chmod(raw_stdout, 0o600)
            os.chmod(stderr_path, 0o600)
            code, _, _ = owned_call(argv, env, args.time_limit, work, data, (out, err))
        record["native_exit"] = code
        try:
            read_regular(usage, META_BYTES)
            native_usage = strict_json(usage.read_bytes())
            record["usage_state"] = "recorded_not_remaining_allowance"
        except (OSError, ValueError, UnicodeError, Refusal, RecursionError):
            record["usage_state"] = "invalid_or_missing"
        record["raw_stdout_bytes"] = raw_stdout.stat().st_size
        record["proposal_bytes"] = 0
        if code:
            record["outcome"], exit_code = "native_failed", 1
        else:
            try:
                text = proposal_from_jsonl(raw_stdout.read_bytes())
                blob = text.encode("utf-8")
            except (Refusal, OSError, UnicodeError, RecursionError):
                blob = b""
            if blob.strip():
                private_file(proposal, blob)
                record["proposal_bytes"] = len(blob)
                record["proposal_source"] = "assistant.message"
                record["outcome"], exit_code = "proposal_recorded", 0
            else:
                record["outcome"], exit_code = INVALID, 2
    except KeyboardInterrupt:
        exit_code = 130
        if record is not None:
            record["outcome"] = "interrupted"
    except (Refusal, OSError, ValueError, UnicodeError, subprocess.SubprocessError) as error:
        state = str(error) if isinstance(error, Refusal) else "local_failure"
        if record is not None:
            record["outcome"] = state
        print("Copilot adapter: " + state, file=sys.stderr)
        exit_code = 124 if state == "timeout" else 2
    finally:
        if record is not None:
            record["budget_telemetry"] = run_telemetry(record, native_usage)
            record.update(adapter_exit=exit_code, elapsed_seconds=round(time.monotonic() - started, 3), finished_at=date())
            receipt.write_text(json.dumps(record, indent=2) + "\n")
            if os.environ.get("UNIO_ADAPTER_OUTCOME"):
                try:
                    import runpy
                    runpy.run_path(str(Path(__file__).with_name("adapter-outcome.py")))["emit"](
                        "copilot", record, prompt, exit_code, record.get("native_exit"))
                except Exception:
                    pass  # Optional evidence must never replace the real exit.
            print(json.dumps({"receipt": str(receipt), "adapter_exit": exit_code, "native_exit": record["native_exit"],
                              "outcome": record["outcome"], "proposal": record["proposal_path"]}))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
