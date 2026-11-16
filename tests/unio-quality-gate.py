#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Fast regressions for the quality-gate runner itself.

Everything here runs against temporary fixture catalogues and marker
commands: no real suite, no installer run, no network, no long gate. The
tracked baseline snapshot (tests/fixtures/quality-gate-baseline.json) is an
independent record of the original 125-command gate; comparing the live
catalogue against it proves default coverage and order without mirroring
the implementation's own selection predicates.
"""
import json
import os
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATE = ["bash", str(REPO / "tools" / "quality-check.sh")]
CATALOGUE_PATH = REPO / "tools" / "quality-gate-commands.json"
BASELINE_PATH = REPO / "tests" / "fixtures" / "quality-gate-baseline.json"
SUCCESS = "quality-check: all checks passed"
EXPECTED_LANES = [
    "static", "install-smoke", "safety-core", "evidence-review", "managed-lead",
    "adapters", "observation", "bridge", "delegation", "admission-env", "save",
    "docs",
]

ok_count = 0
fail_count = 0


def check(name, condition, detail=""):
    global ok_count, fail_count
    if condition:
        ok_count += 1
        print(f"  ok    {name}")
    else:
        fail_count += 1
        print(f"  FAIL  {name}{' — ' + str(detail) if detail else ''}")


def run_gate(args, catalogue=None, timings=None, tmpdir=None):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if catalogue is not None:
        env["UNIO_QUALITY_GATE_CATALOGUE"] = str(catalogue)
    if timings is not None:
        env["QUALITY_TIMINGS"] = str(timings)
    if tmpdir is not None:
        env["TMPDIR"] = str(tmpdir)
    return subprocess.run(GATE + list(args), env=env, capture_output=True,
                          text=True, timeout=120)


def render_entry(entry):
    parts = [f"{key}={value}" for key, value in entry.get("env", {}).items()]
    parts.extend(entry["argv"])
    text = " ".join(parts)
    if entry.get("stdout_path"):
        text += " > " + entry["stdout_path"]
    return text


def coverage_diff(commands, baseline_commands):
    """Independent comparison of rendered catalogue vs baseline snapshot."""
    problems = []
    rendered = [render_entry(e) for e in commands]
    for index, (got, want) in enumerate(zip(rendered, baseline_commands)):
        if got != want:
            problems.append(f"position {index}: catalogue has {got!r}, baseline has {want!r}")
    if len(rendered) != len(baseline_commands):
        problems.append(f"count {len(rendered)} != baseline {len(baseline_commands)}")
    return problems


def marker_command(cid, marker, lanes):
    return {"id": cid, "argv": ["touch", str(marker)], "lanes": lanes}


def main():
    root = Path(tempfile.mkdtemp(prefix="quality gate selftest "))
    try:
        catalogue = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        commands = catalogue["commands"]
        original = [e for e in commands if not e.get("added_self_test")]
        added = [e for e in commands if e.get("added_self_test")]

        print("catalogue coverage and order")
        check("default coverage equals the baseline snapshot",
              coverage_diff(original, baseline["commands"]) == [],
              coverage_diff(original, baseline["commands"])[:3])
        check("baseline snapshot has the original 125 commands",
              len(baseline["commands"]) == 125, len(baseline["commands"]))
        check("only explicitly added self-tests extend the gate",
              [e["id"] for e in added] == ["test-unio-quality-gate"],
              [e["id"] for e in added])
        check("command ids are unique",
              len({e["id"] for e in commands}) == len(commands))
        check("lane names are exactly the documented twelve",
              catalogue["lanes"] == EXPECTED_LANES, catalogue["lanes"])
        known_lanes = set(catalogue["lanes"])
        check("every command belongs to at least one known lane",
              all(e["lanes"] and set(e["lanes"]) <= known_lanes for e in commands))
        per_lane = {name: 0 for name in catalogue["lanes"]}
        for entry in commands:
            for lane in entry["lanes"]:
                per_lane[lane] += 1
        check("every lane is non-empty",
              all(count > 0 for count in per_lane.values()), per_lane)

        print("planted drift is caught by the baseline comparison")
        check("an omitted command is detected",
              coverage_diff(original[:-1], baseline["commands"]) != [])
        check("an altered command is detected", coverage_diff(
            [{**original[0], "argv": original[0]["argv"] + ["--oops"]}] + original[1:],
            baseline["commands"]) != [])
        swapped = [original[1], original[0]] + original[2:]
        check("a reordered catalogue is detected",
              coverage_diff(swapped, baseline["commands"]) != [])

        print("dry listing against the real catalogue")
        tmp = root / "list tmp"
        tmp.mkdir()
        result = run_gate(["--list"], tmpdir=tmp)
        listed_ids = [line.split("\t", 1)[0] for line in result.stdout.splitlines()
                      if "\t" in line]
        check("full dry listing exits 0",
              result.returncode == 0, result.stderr)
        check("full dry listing shows every command in canonical order",
              listed_ids == [e["id"] for e in commands], len(listed_ids))
        check("dry listing claims no pass",
              "PASS" not in result.stdout.upper() and SUCCESS not in result.stdout)
        check("dry listing creates no fixture directory",
              not any(tmp.iterdir()), list(tmp.iterdir()))
        result = run_gate(["--list", "--lane", "static"], tmpdir=tmp)
        static_ids = [e["id"] for e in commands if "static" in e["lanes"]]
        listed_ids = [line.split("\t", 1)[0] for line in result.stdout.splitlines()
                      if "\t" in line]
        check("lane dry listing shows the lane in canonical order",
              result.returncode == 0 and listed_ids == static_ids, result.stderr)
        result = run_gate(["--list", "--lane", "static", "--lane", "docs"], tmpdir=tmp)
        listed_ids = [line.split("\t", 1)[0] for line in result.stdout.splitlines()
                      if "\t" in line]
        overlap = [e["id"] for e in commands
                   if {"static", "docs"}.intersection(e["lanes"])]
        check("overlapping lanes deduplicate in a dry listing",
              result.returncode == 0 and listed_ids == overlap
              and len(listed_ids) == len(set(listed_ids)), listed_ids)

        print("fixture catalogue behaviour")
        markers = root / "markers dir"
        markers.mkdir()
        m1 = markers / "one marker.txt"
        m2 = markers / "two marker.txt"
        m3 = markers / "three marker.txt"
        order_log = markers / "order log.txt"
        fixture = root / "fixture catalogue.json"
        def fixture_command(cid, marker, lanes):
            return {"id": cid, "lanes": lanes, "argv": [
                "bash", "-c",
                f"touch {shlex.quote(str(marker))}; "
                f"printf '%s\\n' {shlex.quote(cid)} >> {shlex.quote(str(order_log))}"]}
        fixture.write_text(json.dumps({
            "format": 1, "lanes": ["alpha", "beta"],
            "commands": [
                fixture_command("c1", m1, ["alpha"]),
                fixture_command("c2", m2, ["beta"]),
                fixture_command("c3", m3, ["alpha", "beta"]),
            ],
        }))
        tmp = root / "fixture tmp"
        tmp.mkdir()

        result = run_gate(["--list"], catalogue=fixture, tmpdir=tmp)
        check("dry listing of a fixture catalogue runs no commands",
              result.returncode == 0 and not m1.exists() and not m2.exists()
              and not m3.exists() and not any(tmp.iterdir()), result.stdout)

        print("invalid input is rejected before any check or fixture")
        for name, args in [
            ("unknown lane", ["--lane", "nope"]),
            ("unknown flag", ["--bogus"]),
            ("missing --lane value", ["--lane"]),
            ("duplicate lane", ["--lane", "alpha", "--lane", "alpha"]),
        ]:
            result = run_gate(args, catalogue=fixture, tmpdir=tmp)
            check(f"{name} exits 2 and runs nothing",
                  result.returncode == 2 and not m1.exists() and not m2.exists()
                  and not m3.exists() and not any(tmp.iterdir()),
                  (result.returncode, result.stderr))

        print("execution semantics")
        result = run_gate([], catalogue=fixture, tmpdir=tmp)
        check("full fixture run passes with the exact full-gate success string",
              result.returncode == 0 and result.stdout.strip() == SUCCESS,
              (result.returncode, result.stdout, result.stderr))
        check("full run output never says PARTIAL",
              "PARTIAL" not in result.stdout)
        check("commands with spaces in their paths ran",
              m1.exists() and m2.exists() and m3.exists())

        failing = root / "failing catalogue.json"
        never = markers / "never marker.txt"
        failing.write_text(json.dumps({
            "format": 1, "lanes": ["alpha"],
            "commands": [
                {"id": "ok", "argv": ["touch", str(markers / "ok marker.txt")],
                 "lanes": ["alpha"]},
                {"id": "boom", "argv": ["bash", "-c", "exit 7"], "lanes": ["alpha"]},
                {"id": "never", "argv": ["touch", str(never)], "lanes": ["alpha"]},
            ],
        }))
        result = run_gate([], catalogue=failing, tmpdir=tmp)
        check("a failing command's exit code is preserved",
              result.returncode == 7, result.returncode)
        check("the run stops at the first failure",
              not never.exists())
        check("a failed run cleans up its fixture directory",
              not any(tmp.iterdir()), list(tmp.iterdir()))

        print("lane selection, union and labels")
        for path in (m1, m2, m3):
            if path.exists():
                path.unlink()
        order_log.unlink()
        result = run_gate(["--lane", "alpha", "--lane", "beta"],
                          catalogue=fixture, tmpdir=tmp)
        ran = order_log.read_text().splitlines() if order_log.exists() else []
        check("overlapping lanes run each command exactly once, in canonical order",
              result.returncode == 0 and m1.exists() and m2.exists() and m3.exists()
              and ran == ["c1", "c2", "c3"],
              (result.returncode, ran, result.stderr))
        result = run_gate(["--lane", "alpha"], catalogue=fixture, tmpdir=tmp)
        check("a lane run reports PARTIAL coverage and never a full pass",
              result.returncode == 0 and "PARTIAL coverage" in result.stdout
              and SUCCESS not in result.stdout, result.stdout)
        check("the PARTIAL summary names the lanes and the gap",
              "lanes: alpha" in result.stdout and "2 of 3" in result.stdout
              and "1 not run" in result.stdout, result.stdout)

        print("fixture directory lifecycle")
        no_fixture = root / "no fixture catalogue.json"
        no_fixture.write_text(json.dumps({
            "format": 1, "lanes": ["gamma"],
            "commands": [{"id": "g1", "argv": ["bash", "-c", "exit 0"],
                          "lanes": ["gamma"]}],
        }))
        tmp2 = root / "nofix tmp"
        tmp2.mkdir()
        result = run_gate(["--lane", "gamma"], catalogue=no_fixture, tmpdir=tmp2)
        check("no fixture directory is created when no command needs one",
              result.returncode == 0 and not any(tmp2.iterdir()),
              list(tmp2.iterdir()))
        seen = markers / "seen fixture.txt"
        needs_fixture = root / "needs fixture catalogue.json"
        needs_fixture.write_text(json.dumps({
            "format": 1, "lanes": ["delta"],
            "commands": [{"id": "d1", "lanes": ["delta"], "needs_fixture": True,
                          "argv": ["bash", "-c",
                                   f"ls -d -- \"$TMPDIR\"/quality-check-* > {shlex.quote(str(seen))}"]}],
        }))
        result = run_gate(["--lane", "delta"], catalogue=needs_fixture, tmpdir=tmp2)
        check("the fixture directory exists while a needing command runs",
              result.returncode == 0 and seen.exists()
              and "quality-check-" in seen.read_text(), result.stderr)
        check("the fixture directory is removed after the run",
              not any(tmp2.iterdir()), list(tmp2.iterdir()))
        crash = root / "crash fixture catalogue.json"
        crash.write_text(json.dumps({
            "format": 1, "lanes": ["delta"],
            "commands": [{"id": "d2", "lanes": ["delta"], "needs_fixture": True,
                          "argv": ["bash", "-c", "exit 3"]}],
        }))
        result = run_gate(["--lane", "delta"], catalogue=crash, tmpdir=tmp2)
        check("a failing fixture run still cleans up",
              result.returncode == 3 and not any(tmp2.iterdir()),
              (result.returncode, list(tmp2.iterdir())))

        print("environment bounds reach every child command")
        bounds = root / "bounds catalogue.json"
        bounds.write_text(json.dumps({
            "format": 1, "lanes": ["alpha"],
            "commands": [{"id": "b1", "lanes": ["alpha"], "argv": [
                "bash", "-c",
                'test "$UNIO_AUTO_VERIFY" = 0 && test "$UNIO_AUTO_OFF" = 0 && '
                'test "$UNIO_AUTO_SYNC" = 0 && test "$UNIO_CLI_UPDATES_OFFLINE" = 1 && '
                'test "$PYTHONDONTWRITEBYTECODE" = 1']}],
        }))
        result = run_gate([], catalogue=bounds, tmpdir=tmp)
        check("offline and bytecode bounds are exported to children",
              result.returncode == 0, (result.returncode, result.stderr))

        missing_tool = root / "missing tool catalogue.json"
        missing_tool.write_text(json.dumps({
            "format": 1, "lanes": ["alpha"],
            "commands": [{"id": "x1", "argv": ["no-such-unio-tool-xyz"],
                          "lanes": ["alpha"]}],
        }))
        result = run_gate([], catalogue=missing_tool, tmpdir=tmp)
        check("a missing command exits 127 without a traceback",
              result.returncode == 127 and "Traceback" not in result.stderr,
              (result.returncode, result.stderr))

        print("timing records")
        timings_path = root / "timing dir" / "timings.tsv"
        timings_path.parent.mkdir()
        result = run_gate([], catalogue=failing, timings=timings_path, tmpdir=tmp)
        check("a failing run still exits with the command's code",
              result.returncode == 7, result.returncode)
        rows = timings_path.read_text().splitlines()
        check("the timing file has a header and one row per executed command",
              len(rows) == 3 and rows[0].split("\t") ==
              ["id", "command", "start_utc", "end_utc", "elapsed_seconds",
               "exit_code"], rows[:1])
        fields = [row.split("\t") for row in rows[1:]]
        check("timing rows record ids and actual exit codes",
              [f[0] for f in fields] == ["ok", "boom"]
              and [f[5] for f in fields] == ["0", "7"], fields)
        parsed = True
        for f in fields:
            try:
                datetime.fromisoformat(f[2])
                datetime.fromisoformat(f[3])
                parsed = parsed and float(f[4]) >= 0
            except ValueError:
                parsed = False
        check("timestamps parse as ISO 8601 and elapsed is non-negative",
              parsed, fields)
        check("the timing command column carries the rendered command",
              "touch" in fields[0][1] and "exit 7" in fields[1][1], fields)

        print("timing failure handling")
        unusable = root / "unusable timings"
        unusable.mkdir()
        passing = root / "passing catalogue.json"
        passing.write_text(json.dumps({
            "format": 1, "lanes": ["alpha"],
            "commands": [{"id": "p1", "argv": ["bash", "-c", "exit 0"],
                          "lanes": ["alpha"]}],
        }))
        result = run_gate([], catalogue=passing, timings=unusable, tmpdir=tmp)
        check("an unusable timing output cannot produce a false full pass",
              result.returncode not in (0,) and SUCCESS not in result.stdout
              and "timing" in result.stderr.lower(),
              (result.returncode, result.stdout, result.stderr))
        result = run_gate([], catalogue=failing, timings=unusable, tmpdir=tmp)
        check("a timing failure never masks the command's failure code",
              result.returncode == 7 and "timing" in result.stderr.lower(),
              (result.returncode, result.stderr))

        print("bad runner inputs")
        broken = root / "broken catalogue.json"
        broken.write_text("{not json")
        result = run_gate([], catalogue=broken, tmpdir=tmp)
        check("an invalid catalogue fails without a pass claim",
              result.returncode not in (0,) and SUCCESS not in result.stdout
              and "Traceback" not in result.stderr,
              (result.returncode, result.stderr))
        result = run_gate([], catalogue=root / "absent catalogue.json", tmpdir=tmp)
        check("a missing catalogue fails cleanly",
              result.returncode not in (0,) and "Traceback" not in result.stderr,
              (result.returncode, result.stderr))
        bad_lane = root / "bad lane catalogue.json"
        bad_lane.write_text(json.dumps({
            "format": 1, "lanes": ["alpha"],
            "commands": [{"id": "n1", "argv": ["bash", "-c", "exit 0"],
                          "lanes": ["not-a-lane"]}],
        }))
        result = run_gate([], catalogue=bad_lane, tmpdir=tmp)
        check("a command with an unknown lane is rejected",
              result.returncode not in (0,) and "Traceback" not in result.stderr,
              (result.returncode, result.stderr))
        dup_id = root / "duplicate id catalogue.json"
        dup_id.write_text(json.dumps({
            "format": 1, "lanes": ["alpha"],
            "commands": [
                {"id": "same", "argv": ["bash", "-c", "exit 0"], "lanes": ["alpha"]},
                {"id": "same", "argv": ["bash", "-c", "exit 0"], "lanes": ["alpha"]},
            ],
        }))
        result = run_gate([], catalogue=dup_id, tmpdir=tmp)
        check("duplicate command ids are rejected",
              result.returncode not in (0,) and "Traceback" not in result.stderr,
              (result.returncode, result.stderr))
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)

    print()
    print(f"quality-gate selftest: {ok_count} ok, {fail_count} failed")
    return 1 if fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
