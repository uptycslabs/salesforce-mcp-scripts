#!/usr/bin/env python3
"""Install a Salesforce 2GP package across multiple authenticated orgs.

Reads a TOML config that names the package version and the target orgs
(by alias, username, or org ID), then invokes `sf package install` per org.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    sys.exit(
        "Python 3.11+ is required (for the stdlib `tomllib` module). "
        "Current version: " + sys.version.split()[0]
    )


VALID_UPGRADE_TYPES = {"DeprecateOnly", "Mixed", "Delete"}


@dataclass
class InstallResult:
    org: str
    success: bool
    detail: str


def load_config(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def check_sf_cli() -> None:
    if shutil.which("sf") is None:
        sys.exit(
            "Salesforce CLI ('sf') not found on PATH. "
            "Install it from https://developer.salesforce.com/tools/salesforcecli"
        )


def list_authed_orgs() -> set[str]:
    """Return aliases, usernames, and org IDs known to the local sf CLI."""
    proc = subprocess.run(
        ["sf", "org", "list", "--json"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return set()
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return set()
    known: set[str] = set()
    result = data.get("result", {})
    for orgs in result.values():
        if not isinstance(orgs, list):
            continue
        for org in orgs:
            for field in ("alias", "username", "orgId"):
                value = org.get(field)
                if value:
                    known.add(value)
    return known


def install_package(
    org: str,
    package: str,
    installation_key: str | None,
    wait: int,
    publish_wait: int,
    upgrade_type: str | None,
    security_type: str | None,
) -> InstallResult:
    cmd = [
        "sf", "package", "install",
        "--package", package,
        "--target-org", org,
        "--wait", str(wait),
        "--publish-wait", str(publish_wait),
        "--no-prompt",
        "--json",
    ]
    if installation_key:
        cmd += ["--installation-key", installation_key]
    if upgrade_type:
        cmd += ["--upgrade-type", upgrade_type]
    if security_type:
        cmd += ["--security-type", security_type]

    print(f"\n--> Installing {package} into {org} ...")
    proc = subprocess.run(cmd, capture_output=True, text=True)

    try:
        payload = json.loads(proc.stdout) if proc.stdout else {}
    except json.JSONDecodeError:
        payload = {}

    if proc.returncode == 0 and payload.get("status") == 0:
        status = payload.get("result", {}).get("Status", "SUCCESS")
        return InstallResult(org, True, f"Status: {status}")

    message = (
        payload.get("message")
        or proc.stderr.strip()
        or proc.stdout.strip()
        or f"sf exited with code {proc.returncode}"
    )
    return InstallResult(org, False, message)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install a Salesforce 2GP package across multiple authenticated orgs."
    )
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to TOML config (default: ./config.toml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Print what would be installed, then exit without running "
            "`sf package install`. Still requires the `sf` CLI on PATH and "
            "queries `sf org list` to warn about orgs that aren't "
            "authenticated locally."
        ),
    )
    args = parser.parse_args()

    if not args.config.exists():
        sys.exit(f"Config file not found: {args.config}")

    check_sf_cli()
    cfg = load_config(args.config)

    pkg = cfg.get("package") or {}
    package_id = pkg.get("version_id")
    if not package_id:
        sys.exit("Config is missing required [package].version_id (a 04t... id or alias).")

    installation_key = pkg.get("installation_key") or None
    wait = int(pkg.get("wait", 20))
    publish_wait = int(pkg.get("publish_wait", 10))
    upgrade_type = pkg.get("upgrade_type") or None
    security_type = pkg.get("security_type") or None

    if upgrade_type and upgrade_type not in VALID_UPGRADE_TYPES:
        sys.exit(
            f"Invalid [package].upgrade_type='{upgrade_type}'. "
            f"Must be one of: {sorted(VALID_UPGRADE_TYPES)}"
        )

    orgs = cfg.get("orgs")
    if not orgs or not isinstance(orgs, list):
        sys.exit("Config is missing 'orgs' list (array of alias/username/orgId values).")

    known = list_authed_orgs()
    if known:
        missing = [o for o in orgs if o not in known]
        if missing:
            print("Warning: these orgs are not in `sf org list` output:")
            for o in missing:
                print(f"  - {o}")
            print("Authenticate them first with `sf org login web -a <alias>`, "
                  "or correct the value in the config.\n")

    if args.dry_run:
        print(f"DRY RUN: would install {package_id} into:")
        for o in orgs:
            print(f"  - {o}")
        return 0

    results: list[InstallResult] = []
    for org in orgs:
        result = install_package(
            org=org,
            package=package_id,
            installation_key=installation_key,
            wait=wait,
            publish_wait=publish_wait,
            upgrade_type=upgrade_type,
            security_type=security_type,
        )
        marker = "[OK]  " if result.success else "[FAIL]"
        print(f"  {marker} {result.org}: {result.detail}")
        results.append(result)

    print("\n=== Summary ===")
    succeeded = sum(1 for r in results if r.success)
    failed = len(results) - succeeded
    print(f"Succeeded: {succeeded}/{len(results)}")
    if failed:
        print(f"Failed:    {failed}")
        for r in results:
            if not r.success:
                print(f"  - {r.org}: {r.detail}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
