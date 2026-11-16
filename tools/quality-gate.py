#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Quality-gate dispatcher: selectable, measurable, offline.

tools/quality-check.sh execs this module. The full catalogue lives in
tools/quality-gate-commands.json; this file only dispatches it.

Behaviour contract (see docs/development/VALIDATION-MATRIX.md):
- no arguments: the full offline gate — every catalogue command, in catalogue
  order, first failure stops the run and its exit code becomes the gate's.
  Only a complete full run prints "quality-check: all checks passed".
- --lane NAME (repeatable): the union of the named lanes, deduplicated, in
  canonical catalogue order. A successful lane run prints a PARTIAL coverage
  summary and never the full-gate success string.
- --list: dry listing of the selected (or full) command ids and commands.
  It runs nothing, installs nothing, creates no fixture and changes no
  configuration, and never claims a pass.
- unknown flags, unknown lanes, duplicate lanes and missing values exit 2
  before any check or fixture is started.
- QUALITY_TIMINGS (environment, optional): TSV path for per-command records.
  Format: header "id\\tcommand\\tstart_utc\\tend_utc\\telapsed_seconds\\texit_code",
  then one row per executed command, written and flushed incrementally.
  start_utc/end_utc are ISO 8601 UTC; elapsed_seconds is a monotonic-clock
  difference with 6 decimals; exit_code is the command's actual exit code
  (128+signal when a signal killed it). Tabs/newlines inside a field are
  replaced by spaces. A timing failure never masks a check failure; if every
  check passed but the timing output was unusable, the gate exits 1 and does
  not print the success string.
- The private installer fixture (temp directory + install + shellcheck on the
  installed engine) is created only when a selected command needs it, and is
  always removed on exit — including when SIGTERM or SIGHUP terminates the
  gate: the signal is forwarded to the command the gate currently owns (only
  that process), the child is reaped within a bounded wait, and the gate then
  exits 128+signal. Actual command failures keep their own exit codes.
- Environment bounds for every child: UNIO_AUTO_VERIFY=0, UNIO_AUTO_OFF=0,
  UNIO_AUTO_SYNC=0, UNIO_CLI_UPDATES_OFFLINE=1, PYTHONDONTWRITEBYTECODE=1.
  The UNIO_* bounds are the original gate's; PYTHONDONTWRITEBYTECODE=1 is an
  intentional minor addition, so the child environment is not byte-identical
  to the legacy one.
- Control variables QUALITY_TIMINGS and UNIO_QUALITY_GATE_CATALOGUE are never
  inherited by child commands, so a nested gate run (for example the runner
  self-test inside a timed full gate) cannot truncate or corrupt the outer
  timing file. A fixture command that wants either variable must set it
  explicitly in its own env.
- UNIO_QUALITY_GATE_CATALOGUE overrides the catalogue path. It exists for the
  runner's own regression tests (fixture commands) and is not a lane selector.
  Every run made with an override is labelled FIXTURE/noncanonical and never
  prints the canonical success string, so no override can certify the
  production full gate.

There is no parallelism, caching, retry, automatic skip or changed-path
selection in this batch; the default run is serial, as before.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CATALOGUE = REPO / "tools" / "quality-gate-commands.json"
SUCCESS = "quality-check: all checks passed"
CHECK_DIR_PLACEHOLDER = "{check_dir}"
TIMING_HEADER = "id\tcommand\tstart_utc\tend_utc\telapsed_seconds\texit_code"
DEPENDENCIES = ("python3", "shellcheck", "node")
CHILD_CONTROL_VARS = ("QUALITY_TIMINGS", "UNIO_QUALITY_GATE_CATALOGUE")
TERMINATION_SIGNALS = ("SIGTERM", "SIGHUP")
REAP_TIMEOUT_SECONDS = 5


def usage_error(message):
    print(f"quality-check: {message}", file=sys.stderr)
    print("usage: quality-check.sh [--list] [--lane NAME]...", file=sys.stderr)
    raise SystemExit(2)


def parse_args(argv):
    lanes = []
    do_list = False
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--list":
            do_list = True
        elif arg == "--lane":
            i += 1
            if i >= len(argv):
                usage_error("missing value for --lane")
            lanes.append(argv[i])
        elif arg in ("-h", "--help"):
            print(__doc__)
            return None
        else:
            usage_error(f"unknown argument: {arg}")
        i += 1
    return lanes, do_list


def load_catalogue():
    path = Path(os.environ.get("UNIO_QUALITY_GATE_CATALOGUE") or DEFAULT_CATALOGUE)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CatalogueError(f"cannot read catalogue {path}: {exc}")
    except ValueError as exc:
        raise CatalogueError(f"invalid catalogue JSON in {path}: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("lanes"), list):
        raise CatalogueError("catalogue must be an object with a lanes list")
    known_lanes = set(data["lanes"])
    commands = data.get("commands")
    if not isinstance(commands, list) or not commands:
        raise CatalogueError("catalogue must have a non-empty commands list")
    seen = set()
    for entry in commands:
        if not isinstance(entry, dict):
            raise CatalogueError("catalogue command entries must be objects")
        cid = entry.get("id")
        if not isinstance(cid, str) or not cid:
            raise CatalogueError("catalogue command needs a non-empty id")
        if cid in seen:
            raise CatalogueError(f"duplicate command id: {cid}")
        seen.add(cid)
        argv = entry.get("argv")
        if not isinstance(argv, list) or not argv or not all(
            isinstance(a, str) and a for a in argv
        ):
            raise CatalogueError(f"command {cid} needs a non-empty argv of strings")
        lanes_of = entry.get("lanes")
        if (
            not isinstance(lanes_of, list)
            or not lanes_of
            or not all(isinstance(l, str) and l for l in lanes_of)
        ):
            raise CatalogueError(f"command {cid} needs at least one lane")
        unknown = [l for l in lanes_of if l not in known_lanes]
        if unknown:
            raise CatalogueError(f"command {cid} uses unknown lane(s): {', '.join(unknown)}")
    return data


class CatalogueError(Exception):
    pass


def select_commands(data, lanes):
    if not lanes:
        return list(data["commands"])
    wanted = set(lanes)
    return [e for e in data["commands"] if wanted.intersection(e["lanes"])]


def substitute(text, check_dir):
    return text.replace(CHECK_DIR_PLACEHOLDER, check_dir) if check_dir else text


def render(entry, check_dir=None):
    parts = []
    for key, value in entry.get("env", {}).items():
        parts.append(f"{key}={substitute(value, check_dir)}")
    parts.extend(substitute(a, check_dir) for a in entry["argv"])
    text = " ".join(parts)
    if entry.get("stdout_path"):
        text += " > " + substitute(entry["stdout_path"], check_dir)
    return text


def tsv_field(text):
    return str(text).replace("\t", " ").replace("\n", " ").replace("\r", " ")


class TimingLog:
    """Incremental TSV writer; failures are recorded, never raised."""

    def __init__(self, path):
        self.failed = False
        self.handle = None
        if not path:
            return
        try:
            self.handle = open(path, "w", encoding="utf-8")
            self.handle.write(TIMING_HEADER + "\n")
            self.handle.flush()
        except OSError as exc:
            self.failed = True
            self.warn(f"cannot open timing output {path}: {exc}")
            self.handle = None

    @staticmethod
    def warn(message):
        print(f"quality-check: timing output failure: {message}", file=sys.stderr)

    def record(self, entry, check_dir, start_utc, end_utc, elapsed, code):
        if self.failed or self.handle is None:
            return
        row = "\t".join(
            tsv_field(f)
            for f in (
                entry["id"],
                render(entry, check_dir),
                start_utc,
                end_utc,
                f"{elapsed:.6f}",
                code,
            )
        )
        try:
            self.handle.write(row + "\n")
            self.handle.flush()
        except OSError as exc:
            self.failed = True
            self.warn(f"cannot write timing record: {exc}")

    def close(self):
        if self.handle is not None:
            try:
                self.handle.close()
            except OSError:
                pass


def run_gate(data, lanes):
    os.chdir(REPO)
    selection = select_commands(data, lanes)
    if not selection:
        usage_error("the selected lanes contain no commands")

    override = os.environ.get("UNIO_QUALITY_GATE_CATALOGUE", "")
    child_env = dict(os.environ)
    for key in CHILD_CONTROL_VARS:
        child_env.pop(key, None)
    child_env.update(
        {
            "UNIO_AUTO_VERIFY": "0",
            "UNIO_AUTO_OFF": "0",
            "UNIO_AUTO_SYNC": "0",
            "UNIO_CLI_UPDATES_OFFLINE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    for dependency in DEPENDENCIES:
        if any(entry["argv"][0] == dependency for entry in selection):
            if shutil.which(dependency) is None:
                print(f"missing dependency: {dependency}", file=sys.stderr)
                raise SystemExit(1)

    timings = TimingLog(os.environ.get("QUALITY_TIMINGS", ""))
    check_dir = None
    if any(entry.get("needs_fixture") for entry in selection):
        check_dir = tempfile.mkdtemp(prefix="quality-check-")

    owned = {"proc": None}

    def on_termination_signal(signum, frame):
        proc = owned["proc"]
        if proc is not None and proc.poll() is None:
            try:
                proc.send_signal(signum)
            except (ProcessLookupError, OSError):
                pass
        raise SystemExit(128 + signum)

    installed_signals = []
    try:
        for name in TERMINATION_SIGNALS:
            sig = getattr(signal, name, None)
            if sig is None:
                continue
            try:
                installed_signals.append((sig, signal.signal(sig, on_termination_signal)))
            except (OSError, ValueError):
                pass
        for entry in selection:
            argv = [substitute(a, check_dir) for a in entry["argv"]]
            env = dict(child_env)
            for key, value in entry.get("env", {}).items():
                env[key] = substitute(value, check_dir)
            out_handle = None
            if entry.get("stdout_path"):
                out_path = substitute(entry["stdout_path"], check_dir)
                try:
                    out_handle = open(out_path, "w")
                except OSError as exc:
                    print(f"quality-check: cannot open output {out_path}: {exc}", file=sys.stderr)
                    raise SystemExit(1)
            start_mono = time.monotonic()
            start_utc = datetime.now(timezone.utc).isoformat()
            try:
                proc = subprocess.Popen(argv, env=env, cwd=REPO, stdout=out_handle)
            except FileNotFoundError:
                if out_handle is not None:
                    out_handle.close()
                print(f"quality-check: command not found: {argv[0]}", file=sys.stderr)
                raise SystemExit(127)
            owned["proc"] = proc
            try:
                code = proc.wait()
            finally:
                owned["proc"] = None
                if proc.poll() is None:
                    try:
                        proc.wait(timeout=REAP_TIMEOUT_SECONDS)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                if out_handle is not None:
                    out_handle.close()
            end_utc = datetime.now(timezone.utc).isoformat()
            elapsed = time.monotonic() - start_mono
            if code < 0:
                code = 128 - code
            timings.record(entry, check_dir, start_utc, end_utc, elapsed, code)
            if code != 0:
                raise SystemExit(code)
    finally:
        for sig, previous in installed_signals:
            try:
                signal.signal(sig, previous)
            except (OSError, ValueError):
                pass
        if check_dir:
            shutil.rmtree(check_dir, ignore_errors=True)
        timings.close()

    if timings.failed:
        print("quality-check: timing output was unusable; not reporting a pass", file=sys.stderr)
        raise SystemExit(1)
    if lanes:
        total = len(data["commands"])
        if override:
            print(f"quality-check: FIXTURE catalogue {override} (noncanonical)")
        print(f"quality-check: PARTIAL coverage — lanes: {', '.join(lanes)}")
        print(
            f"quality-check: {len(selection)} of {total} full-gate commands ran; "
            f"{total - len(selection)} not run"
        )
    elif override:
        print(
            f"quality-check: FIXTURE catalogue {override} — all fixture commands "
            "passed (noncanonical: not the production catalogue; not a full-gate pass)"
        )
    else:
        print(SUCCESS)


def list_selection(data, lanes):
    override = os.environ.get("UNIO_QUALITY_GATE_CATALOGUE", "")
    if override:
        print(f"quality-check: FIXTURE catalogue {override} (noncanonical)")
    selection = select_commands(data, lanes)
    if lanes:
        print(
            f"quality-check: dry listing — lanes: {', '.join(lanes)} "
            f"({len(selection)} of {len(data['commands'])} commands; PARTIAL coverage)"
        )
    else:
        print(
            f"quality-check: dry listing — full gate "
            f"({len(selection)} commands; no checks were run)"
        )
    for entry in selection:
        print(f"{entry['id']}\t{render(entry)}")


def main(argv):
    parsed = parse_args(argv)
    if parsed is None:
        return 0
    lanes, do_list = parsed
    try:
        data = load_catalogue()
    except CatalogueError as exc:
        print(f"quality-check: invalid catalogue: {exc}", file=sys.stderr)
        raise SystemExit(1)
    known = data["lanes"]
    for lane in lanes:
        if lane not in known:
            usage_error(f"unknown lane: {lane} (available: {', '.join(known)})")
    if len(lanes) != len(set(lanes)):
        usage_error(f"duplicate lane: {next(l for l in lanes if lanes.count(l) > 1)}")
    if do_list:
        list_selection(data, lanes)
        return 0
    run_gate(data, lanes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
