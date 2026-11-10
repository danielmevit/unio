#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Optional, explicitly pinned Vibe worker (2.26.1 and 3.1.1). No dependency installation."""
import argparse
import codecs
from datetime import datetime, timezone
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

# Explicitly validated CLI versions and, per version, the model aliases this
# adapter may request. Anything else refuses before any provider invocation.
# 2.26.1 is the tested pin: process-local VIBE_* model overlay + --output
# streaming. 3.1.1 is validated through the documented --model ALIAS flag with
# --output json (a message list); VIBE_* model overlays are a 2.26.1 mechanism
# only and are never assumed on 3.1.1.
CLI_VERSIONS = {
    "2.26.1": {"models": ("glm-5-3", "mistral-medium-3-5"), "overlay": True},
    "3.1.1": {"models": ("glm-5-3", "mistral-large-4-0-3"), "overlay": False},
}
MODELS = {
    "glm-5-3": ("zai-glm-5-3", "Z.ai", 1.4, .14, 4.4),
    "mistral-medium-3-5": ("mistral-medium-3-5", "Mistral", 1.5, .15, 7.5),
    # Mistral Large 4: exact validated alias/wire pair (selection reference
    # 2026-11-10). Subscription-priced; catalog prices are not billing proof,
    # so the price fields stay None and USD usage remains Unknown, never 0.
    "mistral-large-4-0-3": ("mistral-large-4-0", "Mistral", None, None, None),
}
# Adapter-level thinking selector. On the pinned 2.26.1 CLI the level travels
# only through the process-local model override (all three levels, unchanged).
# 3.1.1 has no per-run thinking control at all (no overlay mechanism, no native
# thinking flag), so only the catalog level "high" observed for the validated
# aliases may run there and a low/medium request refuses before the provider
# (see check_bounds) instead of silently executing the account's existing level.
THINKING_LEVELS = ("low", "medium", "high")
# Supported numeric bounds; the route contract check validates against exactly
# these, on every supported CLI version, so dispatch and execution agree.
# On 3.1.1 each cap may additionally be the documented choice "none", which
# omits the native flag (the CLI default then applies and is recorded from
# the export limits when present). Omission is not an unlimited-provider
# claim and never permits a paid fallback; the owned-process supervisor
# bound below still applies and is recorded separately.
MAX_TOKENS = 16000000
MAX_PRICE_USD = 10.0
MAX_TURNS = 180
MAX_TIME_LIMIT = 7200.0
# Representable parsing bounds: caps are finite decimal integers/floats only
# (no nan/inf/underscores/hex); values beyond the supported bounds above are
# refused before launch, never clamped.
CAP_INT = re.compile(r'[+-]?[0-9]+\Z')
CAP_FLOAT = re.compile(r'[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?\Z')
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

    def __init__(self, stream=None, prompt_bytes=0):
        self.stream = sys.stdout if stream is None else stream
        self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.buffer = ""
        self.discard = False
        self.events = 0
        self.heartbeats = 0
        self.malformed = 0
        self.unlabeled = 0
        self.printed = 0
        self.responses = 0
        self.context_bytes = prompt_bytes
        self.input_estimate = 0
        self.output_estimate = 0
        self.observed_content = False
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
        # Only structural stream entries contribute counters; content is never
        # retained or published. Four UTF-8 bytes/token is a heuristic, not a
        # tokenizer or a measured lower bound. Hidden context/cache are unknown.
        if isinstance(value, dict):
            kind = value.get("type")
            if kind == "message" and value.get("role") in ("user", "assistant"):
                content = value.get("content")
                if isinstance(content, list):
                    size = sum(len(v["text"].encode("utf-8")) for v in content
                               if isinstance(v, dict) and v.get("type") == "text"
                               and isinstance(v.get("text"), str))
                    if value.get("role") == "user" and self.responses == 0:
                        self.context_bytes = max(self.context_bytes, size)
                    elif value.get("role") == "assistant":
                        self.input_estimate += (self.context_bytes + 3) // 4
                        self.output_estimate += (size + 3) // 4
                        self.context_bytes += size
                        self.observed_content = True
                    else:
                        self.context_bytes += size
            elif kind == "effect":
                self.context_bytes += len(line.encode("utf-8"))
            elif kind == "reasoning" and isinstance(value.get("text"), str):
                self.context_bytes += len(value["text"].encode("utf-8"))
        label = self.label(value)
        if label is None:
            self.unlabeled += 1
            return
        self.events += 1
        self.last_label = label
        if label == "assistant response observed":
            self.responses += 1
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
                    assistant_responses=self.responses,
                    last_label=self.last_label, last_observed_at=self.last_observed_at)


def cap_int(text):
    # "none" is the documented omission choice on Vibe 3.1.1 only; the bound
    # check decides that per detected CLI version. The error message never
    # echoes the rejected value.
    if text == "none":
        return None
    if not CAP_INT.match(text):
        raise argparse.ArgumentTypeError(
            "expected a decimal integer within the adapter bounds, or 'none' where the CLI version supports omission")
    return int(text)


def cap_float(text):
    if text == "none":
        return None
    if not CAP_FLOAT.match(text):
        raise argparse.ArgumentTypeError(
            "expected a finite decimal number within the adapter bounds, or 'none' where the CLI version supports omission")
    return float(text)


def base_environment(inherited=None):
    """Strip VIBE_* overlays (a 2.26.1-only mechanism) and disable self-updates."""
    env = {k: v for k, v in (os.environ if inherited is None else inherited).items()
           if not k.startswith("VIBE_") or k == "VIBE_HOME"}
    env.update(VIBE_ENABLE_UPDATE_CHECKS="false", VIBE_ENABLE_AUTO_UPDATE="false",
               PYTHONDONTWRITEBYTECODE="1")
    return env


def model_environment(label, thinking="high", inherited=None, cli_version="2.26.1"):
    # Preserve the original positional (label, inherited_environment) API.
    if isinstance(thinking, dict) and inherited is None:
        inherited, thinking = thinking, "high"
    wire, lab, inp, cache, out = MODELS[label]
    env = base_environment(inherited)
    if CLI_VERSIONS[cli_version]["overlay"]:
        # 2.26.1 tested mechanism: process-local model definition. Never used
        # on 3.1.1, where --model ALIAS is the documented selection instead.
        model = dict(name=wire, alias=label, provider="mistral", thinking=thinking,
                     thinking_levels=[thinking], input_price=inp,
                     cached_input_price=cache, output_price=out)
        env.update(VIBE_ACTIVE_MODEL=label, VIBE_MODELS=json.dumps({label: model}),
                   VIBE_ALLOWED_MODELS=json.dumps([wire]), VIBE_COMPACTION_MODEL=json.dumps(model),
                   VIBE_UTILITY_MODELS=json.dumps({"title": "active", "smart_approve": "active"}),
                   VIBE_SESSION_LOGGING__GENERATE_TITLES="false", VIBE_EXPERIMENTS__ENABLE="false",
                   VIBE_MCP_SERVERS="[]", VIBE_ENABLE_SUBAGENTS="false", VIBE_ENABLE_CONNECTORS="false",
                   VIBE_API_RETRY_MAX_ELAPSED_TIME="0")
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


def export_summary(path, actual_exit, cli_version, requested=None, wire=None, thinking=None,
                   session_path=None):
    value = strict_json(read_regular(path, EXPORT_BYTES))
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise Refusal("invalid_export")
    if value.get("vibe_version") != cli_version or type(value.get("exit_code")) is not int or value["exit_code"] != actual_exit:
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
    # Cached input is included in input_tokens, not added to the total: the
    # reported total is never double-counted.
    if usage is not None and (usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"] or usage["cached_input_tokens"] > usage["input_tokens"]):
        raise Refusal("invalid_export")
    cost = value.get("cost_usd")
    if cost is not None and (type(cost) not in (int, float) or not 0 <= cost <= 10**6 or not math.isfinite(cost)):
        raise Refusal("invalid_export")
    # 3.1.1 exports carry the native limits actually in force (null when the
    # flag was omitted) and a model-call step count; validate them when present
    # so contradictory metadata can never be recorded as a verified selection.
    limits = value.get("limits")
    if limits is not None:
        if not isinstance(limits, dict) or not set(limits) <= {"max_turns", "max_price", "max_tokens", "time_limit_s"}:
            raise Refusal("invalid_export")
        for key, integral in (("max_turns", True), ("max_tokens", True), ("max_price", False), ("time_limit_s", False)):
            item = limits.get(key)
            if item is None:
                continue
            if type(item) is bool or not isinstance(item, (int, float)) or not math.isfinite(item) or item < 0:
                raise Refusal("invalid_export")
            if integral and type(item) is not int:
                raise Refusal("invalid_export")
            if key in ("max_turns", "max_tokens") and item > 2**63 - 1:
                raise Refusal("invalid_export")
    steps = value.get("steps")
    if steps is not None and (type(steps) is not int or not 0 <= steps <= 10**12):
        raise Refusal("invalid_export")
    # The redacted config, plus the owned invocation's bounded session/meta.json,
    # is only inspected for the session model selection; its raw content (or
    # any secret-shaped value) never enters the receipt.
    selection = session_selection({"config": value.get("config")}, requested, wire, thinking,
                                  session=read_session_meta(session_path) if session_path is not None else None) \
        if requested is not None else None
    result = dict(schema_version=1, outcome=value["outcome"], stop_reason=stop,
                  usage={k: usage[k] for k in fields} if usage is not None else None,
                  estimated_cost_usd=cost, limits=limits if isinstance(limits, dict) else None,
                  steps=steps)
    if selection is not None:
        result["session_selection"] = selection
    return result


# Bounded read of the owned invocation's session metadata: the native 3.1.1 CLI
# records the session's actually selected client model under the output
# directory in session/meta.json.
SESSION_META_BYTES = 262144


def read_session_meta(path):
    """Bounded, no-follow read of the owned session/meta.json, or None.

    Missing, oversized, unsafe-shaped or malformed metadata is absent
    evidence: it can never supply, default or invent identity. Only typed
    identifiers are read by the caller; nothing from the file is copied
    into the receipt.
    """
    try:
        value = strict_json(read_regular(path, SESSION_META_BYTES))
    except (OSError, ValueError, UnicodeError, Refusal, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _text(mapping, key):
    value = mapping.get(key) if isinstance(mapping, dict) else None
    return value if isinstance(value, str) and value else None


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _selected_meta(session):
    """Accept the observed session/meta.json shapes: identity keys at top
    level or under a nested config mapping; a shape carrying none of them
    reads None rather than being guessed from another key."""
    for candidate in (session, _mapping(session).get("config")):
        if any(_text(candidate, key) is not None
               for key in ("active_model", "model_name", "thinking")):
            return _mapping(candidate)
    return None


def session_selection(export, requested, wire, thinking, session=None):
    """Verify the per-session model selection from actual selected identity.

    Sources that record what THIS owned invocation actually selected are read
    first, in priority order: the bounded session/meta.json written under the
    output directory, the export config's per-session section, then the
    export config's active_model. routed_model_config/routed_default_model
    describe the account's DEFAULT route: their identifiers are used for the
    selection only when the default declaration itself names the selected
    alias, and are otherwise preserved as separate routed_default_* fields
    (possibly contradicting observations), never as proof of a selection.

    A verified state requires an actual selected alias AND wire name; partial
    or default-only identity metadata stays unknown, never verified. Effort
    has its own provenance: only a declaration attributable to the selected
    model is recorded as session_thinking; missing effort metadata stays
    unknown (None) and is never proof that the requested level took effect.
    Contradictory observations are explicit mismatches. Nothing here is
    server identity evidence: effective model/effort remain Unknown regardless.
    """
    result = dict(state="unknown", session_alias=None, session_wire=None,
                  session_thinking=None, detail="no usable session selection metadata")
    config = _mapping(_mapping(export).get("config"))
    controls = ((_selected_meta(session), "session_meta"),
                (_mapping(config.get("session")), "config_session"))
    # Ordered selected-identity observations: (source, alias, wire).
    selectors = []
    for mapping, source in controls:
        alias, wire_seen = _text(mapping, "active_model"), _text(mapping, "model_name")
        if alias is not None or wire_seen is not None:
            selectors.append((source, alias, wire_seen))
    active = _text(config, "active_model")
    if active is not None:
        selectors.append(("config_active_model", active, None))
    routed = _mapping(config.get("routed_model_config"))
    default_alias = _text(routed, "alias") or _text(config, "routed_default_model")
    default_wire = _text(routed, "name")
    default_thinking = _text(routed, "thinking")
    if default_alias is not None or default_wire is not None or default_thinking is not None:
        result["routed_default_alias"] = default_alias
        result["routed_default_wire"] = default_wire
        result["routed_default_thinking"] = default_thinking
    session_alias = None
    session_wire = None
    mismatches = []
    for source, alias, wire_seen in selectors:
        if alias is not None and session_alias is None:
            session_alias = alias
        elif alias is not None and alias != session_alias:
            mismatches.append("conflicting selected alias claims: " + session_alias
                              + " and " + alias + " (" + source + ")")
        # A wire that names a different model than the selected alias is not
        # attributable to the selection and was flagged by the alias conflict.
        if wire_seen is None or (alias is not None and alias != session_alias):
            continue
        if session_wire is None:
            session_wire = wire_seen
        elif wire_seen != session_wire:
            mismatches.append("conflicting selected wire claims: " + session_wire
                              + " and " + wire_seen + " (" + source + ")")
    # The selected model's own catalog declaration corroborates the identity,
    # and a default declaration may describe the selection only when it names
    # the selected alias. Neither can prove that any selection happened.
    entry = _mapping(_mapping(config.get("models")).get(session_alias)) \
        if session_alias is not None else {}
    for source, value in (("catalog_entry", _text(entry, "name")),
                          ("routed_default_declaration", default_wire
                           if default_alias is not None and default_alias == session_alias else None)):
        if value is None:
            continue
        if session_wire is None:
            session_wire = value
        elif value != session_wire:
            mismatches.append("conflicting selected wire claims: " + session_wire
                              + " and " + value + " (" + source + ")")
    # Effort provenance is separate from identity: an effort observation is
    # attributable only when its own source names no other model, and a
    # catalog/default declaration only when it names the selected alias.
    session_thinking = None
    think_claims = []
    for mapping, source in controls:
        value, alias = _text(mapping, "thinking"), _text(mapping, "active_model")
        if value is not None and alias in (None, session_alias):
            think_claims.append((source, value))
    if session_alias is not None:
        for source, value in (("catalog_entry", _text(entry, "thinking")),
                              ("routed_default_declaration", default_thinking
                               if default_alias is not None and default_alias == session_alias else None)):
            if value is not None:
                think_claims.append((source, value))
    for source, value in think_claims:
        if session_thinking is None:
            session_thinking = value
        elif value != session_thinking:
            mismatches.append("conflicting thinking declarations: " + session_thinking
                              + " and " + value + " (" + source + ")")
    result.update(session_alias=session_alias, session_wire=session_wire,
                  session_thinking=session_thinking)
    if session_alias is not None and session_alias != requested:
        mismatches.append("alias " + session_alias + " != requested " + requested)
    if session_wire is not None and session_wire != wire:
        mismatches.append("wire " + session_wire + " != expected " + wire)
    if session_thinking is not None and session_thinking != thinking:
        mismatches.append("thinking " + session_thinking + " != requested " + thinking)
    if mismatches:
        result["state"] = "mismatch"
        result["detail"] = "; ".join(mismatches)
        return result
    if session_alias is None or session_wire is None:
        result["state"] = "unknown"
        result["detail"] = ("insufficient actual selected identity: "
                            + ("no selected alias" if session_alias is None else "no selected wire")
                            + "; partial, default-only or catalog-only metadata cannot verify a selection")
        return result
    result["state"] = "verified"
    notes = ["selected alias/wire verified from session metadata"]
    if session_thinking is None:
        notes.append("no session effort metadata; session effort unknown, never proof the requested level took effect")
    else:
        notes.append("declared thinking " + session_thinking + " matches the requested level")
    if default_alias is not None and default_alias != session_alias:
        notes.append("routed default " + default_alias + " differs; recorded as the account default, not this session's selection")
    result["detail"] = "; ".join(notes)
    return result


def parse_output_messages(raw):
    """Bounded provenance for a 3.1.1 --output json message list.

    The list is the run's message history; the actual final completed
    assistant reply is the LAST assistant entry, which can carry a verdict or
    summary absent from the saved export report. Only typed counters and
    hashes are returned: raw bytes stay in the private native stdout log and
    no message content ever enters the receipt or public stdout.

    The validated assistant content forms are a plain string (the shape real
    3.1.1 captures use) and a list of typed text blocks; both are counted.
    "present" requires actual final text bytes: a trailing tool-call-only
    entry, an empty final acknowledgment or an unvalidated content shape
    yields "final_without_text" and is never proof of a completed delivery.
    The state is kept separate from the CLI exit, the export verdict and any
    required artifact; an earlier acknowledgment is never selected instead.
    """
    result = dict(state="invalid", message_count=0, assistant_messages=0,
                  final_index=None, final_sha256=None, final_bytes=None,
                  final_text_bytes=None, final_content_form=None)
    try:
        text = raw.decode("utf-8", errors="strict")
    except (UnicodeError, RecursionError):
        return result
    # The documented 3.1.1 --output json payload is one top-level message
    # list and nothing else on stdout; any extra or malformed output is
    # recorded as invalid rather than partially trusted. Within a valid list
    # the final reply is the LAST assistant entry, never an arbitrary earlier
    # acknowledgement.
    try:
        value = strict_json(text)
    except (ValueError, RecursionError):
        return result
    if not isinstance(value, list):
        return result
    result["message_count"] = len(value)
    final = None
    final_index = None
    assistants = 0
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        if item.get("role") == "assistant":
            assistants += 1
            final = item
            final_index = index
    result["assistant_messages"] = assistants
    if final is None:
        result["state"] = "no_final_assistant"
        return result
    payload = json.dumps(final, sort_keys=True, ensure_ascii=False).encode("utf-8")
    text_bytes = 0
    content = final.get("content")
    if isinstance(content, str):
        result["final_content_form"] = "string"
        text_bytes = len(content.encode("utf-8"))
    elif isinstance(content, list):
        result["final_content_form"] = "blocks"
        text_bytes = sum(len(block["text"].encode("utf-8")) for block in content
                         if isinstance(block, dict) and block.get("type") == "text"
                         and isinstance(block.get("text"), str))
    result["state"] = "present" if text_bytes > 0 else "final_without_text"
    result.update(final_index=final_index,
                  final_sha256=hashlib.sha256(payload).hexdigest(),
                  final_bytes=len(payload), final_text_bytes=text_bytes)
    return result


def contract_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "unio_adapter_contract", str(Path(__file__).with_name("adapter-contract.py")))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, choices=MODELS)
    parser.add_argument("--thinking", choices=THINKING_LEVELS, default="high",
                        help="Adapter-level model thinking level; high is the default")
    parser.add_argument("--prompt-file", help="Regular UTF-8 task; otherwise TASKFILE")
    parser.add_argument("--receipt-dir", required=True, help="Existing private parent; each invocation creates a new run")
    parser.add_argument("--max-price", type=cap_float, default=5.0,
                        help="USD cap, or 'none' to omit the native cap on Vibe 3.1.1")
    parser.add_argument("--max-tokens", type=cap_int, default=2000000,
                        help="cumulative token cap, or 'none' to omit the native cap on Vibe 3.1.1")
    parser.add_argument("--time-limit", type=cap_float, default=5400,
                        help="seconds cap, or 'none' to omit the native cap on Vibe 3.1.1")
    parser.add_argument("--max-turns", type=cap_int, default=120,
                        help="turn cap, or 'none' to omit the native cap on Vibe 3.1.1")
    return parser


def check_bounds(args, cli_version=None):
    """Shared bound validator: the run and the route contract check agree.

    With cli_version None (the offline preflight) the union of documented
    choices is accepted; the run narrows per detected CLI version before any
    provider invocation, so a value the installed CLI cannot honor is refused
    explicitly, never clamped or silently substituted.
    """
    problems = []
    allow_none = cli_version in (None, "3.1.1")
    # 3.1.1 has no adapter-supported per-run thinking control: the VIBE_* model
    # overlay is a 2.26.1-only mechanism and the 3.1.1 CLI documents no thinking
    # flag, so a requested low/medium would silently execute the account's
    # existing catalog level. There is no honest subset to run, so such a
    # request is refused before any provider invocation. "high" is accepted
    # only because it matches the catalog declaration observed for the
    # validated aliases (selection reference 2026-11-10); the adapter claims no
    # control and records the effective effort as Unknown either way.
    if cli_version == "3.1.1" and args.thinking != "high":
        problems.append("--thinking " + args.thinking + " is not supported on Vibe 3.1.1: "
                       "the CLI has no per-run thinking control (model overlays are a 2.26.1-only "
                       "mechanism and no native thinking flag exists), so the request would "
                       "silently execute the account's existing level; keep 3.1.1 runs at the "
                       "observed catalog level high with the effective effort recorded as "
                       "unknown, or use the pinned 2.26.1 route for low/medium control; "
                       "edit the agents.conf route and retry")
    caps = (("--max-price", args.max_price, MAX_PRICE_USD, "float", "USD"),
            ("--max-tokens", args.max_tokens, MAX_TOKENS, "int", "tokens; edit the agents.conf route and retry"),
            ("--max-turns", args.max_turns, MAX_TURNS, "int", "turns"),
            ("--time-limit", args.time_limit, MAX_TIME_LIMIT, "float", "seconds"))
    for flag, value, bound, kind, unit in caps:
        if value is None:
            if not allow_none:
                problems.append(flag + " none (omitted native cap) is only supported on Vibe 3.1.1; "
                                "select a numeric bound for this CLI version")
            continue
        if kind == "int":
            if not 0 < value <= bound:
                problems.append(flag + " " + str(value)
                                + " is outside the supported bound 1.." + str(bound) + " " + unit)
        else:
            if not math.isfinite(value) or not 0 < value <= bound:
                problems.append(flag + " " + str(value)
                                + " is outside the supported bound (0, " + str(bound) + "] " + unit)
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


def run_telemetry(record, progress):
    """Bounded per-run budget telemetry; reported only by a valid export."""
    module = budget_module()
    if module is None:
        return None
    export = record.get("export") if record.get("export_state") == "valid" else None
    usage = export.get("usage") if isinstance(export, dict) else None
    cost = export.get("estimated_cost_usd") if isinstance(export, dict) else None
    requested = record.get("native_limits") if isinstance(record.get("native_limits"), dict) else {}
    observed = export.get("limits") if isinstance(export, dict) and isinstance(export.get("limits"), dict) else None
    # Meter caps prefer the native limits the export actually enforced (null
    # when the owner omitted the cap on 3.1.1) and fall back to the requested
    # values; a null cap is an unknown native default, never "unlimited".
    limits = {}
    for key in ("max_tokens", "max_price", "max_turns"):
        limits[key] = observed.get(key) if observed is not None and key in observed else requested.get(key)
    notes = [module.NOTE_RESENDS]
    if isinstance(usage, dict):
        tokens = module.meter(usage.get("total_tokens"), limits.get("max_tokens"), "reported")
    else:
        if progress is not None and progress.observed_content:
            tokens = module.meter(progress.input_estimate + progress.output_estimate,
                                  limits.get("max_tokens"), "estimated")
            notes.append("partial stream estimate: 4 UTF-8 bytes/token, cumulative observed context re-sent per assistant turn; excludes hidden system/tools, cache and unobserved calls; not a measured lower bound")
        else:
            tokens = module.meter(None, limits.get("max_tokens"), "unknown")
            notes.append("no usage and no completed assistant stream entries; cumulative tokens cannot be estimated reliably")
    prices = MODELS.get(record.get("requested_model"))
    priced = prices is not None and prices[2] is not None and prices[3] is not None and prices[4] is not None
    if cost is not None and priced:
        usd = module.meter(cost, limits.get("max_price"), "reported")
    elif priced and isinstance(usage, dict):
        inp, out, cached = usage["input_tokens"], usage["output_tokens"], usage["cached_input_tokens"]
        estimate = ((inp - cached) * prices[2] + cached * prices[3] + out * prices[4]) / 1000000
        usd = module.meter(estimate, limits.get("max_price"), "estimated")
        notes.append("USD estimated from reported tokens and configured model prices; not subscription spend or remaining allowance")
    elif priced and progress is not None and progress.observed_content:
        estimate = (progress.input_estimate * prices[2] + progress.output_estimate * prices[4]) / 1000000
        usd = module.meter(estimate, limits.get("max_price"), "estimated")
        notes.append("partial USD estimate uses stream token estimates and configured uncached model prices; cache and hidden usage unknown")
    else:
        usd = module.meter(None, limits.get("max_price"), "unknown")
        if priced:
            notes.append("no usage and no completed assistant stream entries; USD cannot be estimated; unknown, not zero")
        else:
            # An unpriced alias: even a native cost figure derives from
            # unproven catalog rates, so the meter stays unknown, never 0.
            notes.append(module.NOTE_UNPRICED)
    final = record.get("final_response") if isinstance(record.get("final_response"), dict) else None
    if progress is not None and progress.responses:
        turns = module.meter(progress.responses, limits.get("max_turns"), "estimated")
        notes.append(module.NOTE_TURNS_COUNTED)
    elif final is not None and final.get("state") in ("present", "final_without_text"):
        # A valid message list counts assistant entries as a turn estimate even
        # when its final entry carried no text; that never proves a completed
        # delivery (final_response state is kept separate from this meter).
        turns = module.meter(final.get("assistant_messages"), limits.get("max_turns"), "estimated")
        notes.append("turns are the count of assistant entries in the 3.1.1 --output json message list; the native export's step count is model calls, not turns")
    else:
        turns = module.meter(None, limits.get("max_turns"), "unknown")
    return module.telemetry(tokens=tokens, turns=turns, usd=usd, notes=notes)


def contract_validate(argv):
    return contract_module().validate(build_parser(), check_bounds, argv, "vibe")


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
    progress = None
    started = time.monotonic()
    exit_code = 2
    try:
        problems = check_bounds(args)
        if problems:
            raise Refusal("; ".join(problems))
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
        # Version preflight with a neutral environment: no VIBE_* model
        # overlay (a 2.26.1-only mechanism) is assumed before the version is
        # known. Unknown versions refuse here, before any provider invocation.
        code, version = owned_call([cli, "--version"], base_environment(), 15, output_limit=4096)
        detected = version.decode("ascii", errors="strict").strip() if code == 0 else ""
        cli_version = detected[5:] if detected.startswith("vibe ") else None
        if cli_version not in CLI_VERSIONS:
            raise Refusal("unsupported_cli")
        # The same shared validator narrows per detected version before launch.
        problems = check_bounds(args, cli_version)
        if problems:
            raise Refusal("; ".join(problems))
        if args.model not in CLI_VERSIONS[cli_version]["models"]:
            raise Refusal("unsupported_model_for_cli_version")
        env, wire, lab = model_environment(args.model, args.thinking, cli_version=cli_version)
        directory = Path(tempfile.mkdtemp(prefix="vibe-run-", dir=parent))
        receipt = directory / "receipt.json"
        task = directory / "task.md"
        with task.open("xb") as out:
            os.chmod(task, 0o600)
            out.write(data)
        export = directory / "native"
        export.mkdir(mode=0o700)
        record = dict(schema_version=1, started_at=date(), cli_version=cli_version,
                      requested_model=args.model, configured_wire_model=wire, ai_lab=lab,
                      transport="Mistral Vibe", budget_group="mistral",
                      requested_effort=args.thinking, requested_thinking=args.thinking,
                      configured_wire_effort=args.thinking if cli_version == "2.26.1" else "unknown",
                      effective_model="unknown", effective_effort="unknown",
                      remaining_allowance="unknown", task_sha256=hashlib.sha256(data).hexdigest(),
                      native_limits=dict(max_price=args.max_price, max_tokens=args.max_tokens,
                                         time_limit=args.time_limit, max_turns=args.max_turns),
                      omitted_caps=[flag for flag, value in
                                    (("max_price", args.max_price), ("max_tokens", args.max_tokens),
                                     ("time_limit", args.time_limit), ("max_turns", args.max_turns))
                                    if value is None],
                      invocations=1, invocation_retries=0, process_exit=None, outcome="starting")
        receipt.write_text(json.dumps(record, indent=2) + "\n")
        # 3.1.1 uses the documented --model ALIAS selection and --output json
        # (a message list whose final completed assistant reply can carry a
        # verdict/summary absent from the saved export). 2.26.1 keeps its
        # exact tested shape: overlay env, all caps, --output streaming.
        cap_args = []
        for flag, value in (("--max-price", args.max_price), ("--max-tokens", args.max_tokens),
                            ("--time-limit", args.time_limit), ("--max-turns", args.max_turns)):
            if value is not None:
                cap_args.extend([flag, str(value)])
        if cli_version == "3.1.1":
            argv = [cli, "--model", args.model, "--prompt-file", str(task),
                    "--workdir", str(Path.cwd()), "--trust", "--agent", "auto-approve"]
            argv += cap_args
            argv += ["--output-dir", str(export), "--output", "json"]
            output_mode = "json"
        else:
            argv = [cli, "--prompt-file", str(task), "--workdir", str(Path.cwd()), "--trust",
                    "--agent", "auto-approve"]
            argv += cap_args
            argv += ["--output-dir", str(export), "--output", "streaming"]
            output_mode = "streaming"
        for name in ("bash", "read_file", "write_file", "edit", "grep"):
            argv.extend(["--enabled-tools", name])
        # The owned-process supervisor bound is separate from the requested
        # CLI time limit (and from the outer UNIO_TIMEOUT): when the owner
        # omits --time-limit on 3.1.1, supervision still applies at the
        # documented maximum plus shutdown margin.
        supervisor_seconds = (args.time_limit if args.time_limit is not None else MAX_TIME_LIMIT) + 20
        record["supervisor_seconds"] = supervisor_seconds
        progress = Progress(prompt_bytes=len(data))
        if output_mode == "json":
            # Capture the bounded message list, keep the raw bytes private,
            # and parse provenance afterwards; heartbeats still report liveness.
            code, captured = owned_call(argv, env, supervisor_seconds, None, progress=progress)
            with (directory / "native-stdout.log").open("xb") as log:
                log.write(captured)
            record["output_mode"] = output_mode
            record["final_response"] = parse_output_messages(captured)
        else:
            record["output_mode"] = output_mode
            with (directory / "native-stdout.log").open("xb") as log:
                code, _ = owned_call(argv, env, supervisor_seconds, log, progress=progress)
        record["process_exit"] = code
        record["outcome"] = "process_finished"
        exit_code = code if code in (0, 1, 2, 3, 4) else 2
        try:
            record["export"] = export_summary(export / "export.json", code, cli_version,
                                              requested=args.model, wire=wire, thinking=args.thinking,
                                              session_path=export / "session" / "meta.json")
            if code == 0 and record["export"]["outcome"] != "finished":
                raise Refusal("inconsistent_export")
            record["export_state"] = "valid"
            record["session_selection"] = record["export"].get("session_selection") or dict(
                state="unknown", session_alias=None, session_wire=None,
                session_thinking=None, detail="no usable model metadata")
        except (OSError, ValueError, UnicodeError, Refusal, TypeError, OverflowError, RecursionError):
            record["export_state"] = "invalid_or_missing"
            record["session_selection"] = dict(state="unknown", session_alias=None, session_wire=None,
                                               session_thinking=None, detail="no valid export metadata")
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
            try:
                import runpy
                record["stop_reason"] = runpy.run_path(str(Path(__file__).with_name("adapter-outcome.py")))["classify"]("vibe", record)
            except Exception:
                record["stop_reason"] = "unknown"
            record["budget_telemetry"] = run_telemetry(record, progress)
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
                     "process_exit": record["process_exit"], "export_state": record.get("export_state", "unknown"),
                     "cli_version": record.get("cli_version", "unknown"),
                     "selection": record.get("session_selection", {}).get("state", "unknown")}
            if record.get("final_response"):
                final["final_response"] = record["final_response"].get("state", "unknown")
            if progress is not None:
                final.update(progress_events=progress.events, progress_last_label=progress.last_label)
            print(json.dumps(final))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
