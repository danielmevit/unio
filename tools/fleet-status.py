#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Fleet observation snapshot."""

import argparse
import datetime
import json
import math
import os
import signal
import subprocess
import sys

def parse_json(data):
    try:
        obj = json.loads(data)
        if not isinstance(obj, dict):
            return None
        def check_finite(x):
            if isinstance(x, float) and not math.isfinite(x):
                raise ValueError("non-finite float")
            elif isinstance(x, dict):
                for v in x.values(): check_finite(v)
            elif isinstance(x, list):
                for v in x: check_finite(v)
        check_finite(obj)
        return obj
    except Exception:
        return None

def run_json_cmd(runner, root, cmd, timeout):
    """Run a runner command and return parsed json or a failure reason enum."""
    try:
        proc = subprocess.Popen(
            [runner] + cmd,
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid,
        )
    except Exception:
        return None, "launch_failed"

    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        if len(stdout) + len(stderr) > 256 * 1024:
            os.killpg(proc.pid, signal.SIGKILL)
            return None, "overflow"
        if proc.returncode != 0:
            return None, "error"
        obj = parse_json(stdout.decode('utf-8'))
        if obj is None:
            return None, "malformed"
        return obj, None
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        proc.communicate()
        return None, "timeout"
    except Exception:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        proc.communicate()
        return None, "malformed"

def main():
    parser = argparse.ArgumentParser(prog="unio fleet", description="Local fleet observation.")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--timeout", type=int, default=10, help="Observation timeout")
    parser.add_argument("--project", help="Explicit project root")

    # parse_known_args will handle --help and exit 0
    parsed_args, _ = parser.parse_known_args(sys.argv[3:])

    if len(sys.argv) < 3:
        sys.stderr.write("usage: fleet-status.py <runner> <root> [--json] [--timeout SECONDS]\n")
        sys.exit(2)

    runner = sys.argv[1]
    root = sys.argv[2]

    timeout = parsed_args.timeout
    if timeout < 1 or timeout > 60:
        sys.stderr.write("timeout must be 1..60\n")
        sys.exit(2)

    if not os.path.isdir(os.path.join(root, "coord")):
        sys.stderr.write("no coord/ under project root\n")
        sys.exit(2)

    stop_file = os.path.join(root, "coord", "STOP")
    is_stop = os.path.exists(stop_file)

    policy_json, p_err = run_json_cmd(runner, root, ["policy", "--json"], timeout)
    agents_json, a_err = run_json_cmd(runner, root, ["agents", "--json"], timeout)
    cap_json, c_err = run_json_cmd(runner, root, ["capacity", "show", "--json"], timeout)
    ccap_json, cc_err = run_json_cmd(runner, root, ["capacity", "show", "--provider", "codex", "--json"], timeout)
    read_json, r_err = run_json_cmd(runner, root, ["readiness", "show", "--json"], timeout)

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    report = {
        "schema_version": 1,
        "project": root,
        "timestamp": now,
        "stop": is_stop,
        "policy_status": "ok" if p_err is None else p_err,
        "agents_status": "ok" if a_err is None else a_err,
        "mode": "unknown",
        "tier": "unknown",
        "lead_agent": None,
        "groups": {}
    }

    if p_err is None and policy_json and policy_json.get("schema_version") == 1:
        report["mode"] = policy_json.get("mode", "unknown")
        report["tier"] = policy_json.get("tier", "unknown")
        report["lead_agent"] = policy_json.get("lead_agent")

        accounts = policy_json.get("accounts", {})
        limit = policy_json.get("workflow_limit_per_group", 1)
        active = policy_json.get("active_with_lead", {})

        # Build groups based on all known agents in agents.json
        if a_err is None and agents_json and agents_json.get("schema_version") == 1:
            for ag in agents_json.get("agents", []):
                name = ag.get("name")
                if not name: continue
                group_name = accounts.get(name, name)

                if group_name not in report["groups"]:
                    report["groups"][group_name] = {
                        "limit": limit,
                        "occupied": active.get(group_name, 0),
                        "agents": {}
                    }

                group = report["groups"][group_name]

                reasons = []
                if is_stop: reasons.append("project_STOP")
                if ag.get("bench", {}).get("off", False): reasons.append("agent_off")
                if not ag.get("binary", {}).get("present", False): reasons.append("binary_missing")
                if group["occupied"] >= group["limit"]: reasons.append("group_full")

                state = "clear"
                if reasons: state = "blocked"

                # Extract readiness for this agent
                auth_info = "unknown"
                if r_err is None and read_json and read_json.get("schema_version") == 1:
                    ag_read = read_json.get("agents", {}).get(name)
                    if ag_read:
                        auth_info = {
                            "status": ag_read.get("status"),
                            "observed_at": ag_read.get("observed_at"),
                            "age_seconds": ag_read.get("age_seconds")
                        }

                group["agents"][name] = {
                    "admission_state": state,
                    "reasons": reasons,
                    "cached_auth": auth_info
                }

        # Attach capacity info to groups
        if c_err is None and cap_json and cap_json.get("schema_version") == 1:
            for gname, gdata in cap_json.get("groups", {}).items():
                if gname in report["groups"]:
                    report["groups"][gname]["manual_allowance"] = {
                        "state": gdata.get("state"),
                        "freshness": gdata.get("freshness"),
                        "observed_at": gdata.get("observed_at"),
                        "age_seconds": gdata.get("age_seconds"),
                        "buckets": gdata.get("buckets", {})
                    }
        if cc_err is None and ccap_json and ccap_json.get("schema_version") == 1:
            for gname, gdata in ccap_json.get("groups", {}).items():
                if gname in report["groups"]:
                    report["groups"][gname]["cached_allowance"] = {
                        "state": gdata.get("state"),
                        "freshness": gdata.get("freshness"),
                        "observed_at": gdata.get("observed_at"),
                        "age_seconds": gdata.get("age_seconds"),
                        "buckets": gdata.get("buckets", {})
                    }
    else:
        # If policy is missing, everything is unknown
        pass

    if parsed_args.json:
        print(json.dumps(report, indent=2))
        return 0

    # Text view
    print(f"Project: {root}")
    summary = f"Mode: {report['mode']} | Tier: {report['tier']}"
    if report['lead_agent']:
        summary += f" | Lead: {report['lead_agent']}"
    if report['stop']:
        summary += " | STOP: active"
    print(summary)

    if report['policy_status'] != 'ok' or report['agents_status'] != 'ok':
        print(f"\nWarning: local inputs unavailable (policy: {report['policy_status']}, agents: {report['agents_status']}). State is Unknown.")
        return 0

    for gname, gdata in report["groups"].items():
        print(f"\nGroup [{gname}] - Occupied: {gdata['occupied']}/{gdata['limit']}")

        # Allowance
        for allowance_type, allowance_key in [("Manual Allowance", "manual_allowance"), ("Cached Allowance", "cached_allowance")]:
            if allowance_key in gdata:
                ad = gdata[allowance_key]
                print(f"  {allowance_type}: {ad.get('state')} ({ad.get('freshness')}), age: {ad.get('age_seconds', 'unknown')}s")
                for bname, bdata in ad.get('buckets', {}).items():
                    for wname, wdata in bdata.get('windows', {}).items():
                        up = wdata.get('usable_remaining_percent')
                        lp = wdata.get('last_reading_remaining_percent')
                        rem = up if up is not None else lp
                        print(f"    Bucket [{bname}] Window [{wname}]: {wdata.get('status')} - remaining: {rem}% (resets at {wdata.get('reset_at')})")

        for aname, adata in gdata["agents"].items():
            state = adata["admission_state"]
            reasons = ", ".join(adata["reasons"]) if adata["reasons"] else "all local checks clear"

            auth_str = "unknown"
            if isinstance(adata["cached_auth"], dict):
                auth_str = f"{adata['cached_auth'].get('status')} (age {adata['cached_auth'].get('age_seconds')}s)"

            print(f"  Agent {aname}: {state.upper()} ({reasons}) | Cached auth: {auth_str}")

    print("\nNote: Observation reflects cached readings and local facts only. External sessions and provider readiness are uncounted.")
    return 0

if __name__ == '__main__':
    sys.exit(main())
