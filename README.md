# Salesforce 2GP multi-org installer

A small Python script that installs a Salesforce second-generation (2GP)
managed/unlocked package into many orgs in one run. It shells out to the
official Salesforce CLI (`sf`) and reuses the orgs you have already
authenticated locally — no credentials are stored in config.

## Requirements

- **Python 3.11+** (uses the stdlib `tomllib` module — no `pip install` needed).
- **Salesforce CLI** `sf` v2 on your `PATH`.
  Install: <https://developer.salesforce.com/tools/salesforcecli>
  Verify with `sf --version`.

## Setup

1. Clone / copy this directory.
2. Authenticate every target org with the Salesforce CLI, giving each an
   alias so the config stays readable:

   ```sh
   sf org login web --alias prod-org
   sf org login web --alias qa-org
   # ...one per org
   ```

   You can confirm the orgs the CLI knows about with:

   ```sh
   sf org list
   ```

   The script will warn if a config entry doesn't appear in that list.

3. Create your config from the example:

   ```sh
   cp config.example.toml config.toml
   ```

4. Edit `config.toml`:
   - `[package].version_id` — the `04t...` Subscriber Package Version Id
     (or a package alias defined in your `sfdx-project.json`).
   - `[package].installation_key` — only if the package version was
     built with an installation key.
   - `orgs` — a list of org identifiers. Each entry may be an **alias**,
     a **username**, or an **org id** (anything `sf` accepts for
     `--target-org`). Aliases are recommended for readability.

   Other knobs (`wait`, `publish_wait`, `upgrade_type`, `security_type`)
   are documented inline in `config.example.toml`.

## Usage

Dry run — shows the package and orgs the script would touch without
running `sf package install`:

```sh
python3 install_package.py --config config.toml --dry-run
```

Dry run still requires the `sf` CLI on your `PATH` and calls
`sf org list` to warn about config entries that aren't authenticated
locally. It just stops short of invoking `sf package install`. If you
need to validate a config on a machine without `sf` installed, copy it
to a machine that has the CLI authenticated against the target orgs.

Real run:

```sh
python3 install_package.py --config config.toml
```

`--config` defaults to `./config.toml`, so once the file is in place you
can simply run:

```sh
python3 install_package.py
```

## What the script does per org

For each org in `orgs`, it runs the equivalent of:

```sh
sf package install \
  --package <version_id> \
  --target-org <org> \
  --wait <wait> \
  --publish-wait <publish_wait> \
  --no-prompt \
  --json
```

…plus `--installation-key`, `--upgrade-type`, and `--security-type` when
configured. Results are parsed from the `--json` output and a per-org
status line is printed, followed by a final summary. The script exits
non-zero if any org fails so it composes cleanly with CI.

## Troubleshooting

- **"Salesforce CLI ('sf') not found on PATH"** — install the CLI and
  reopen your shell; `which sf` should print a path.
- **"orgs are not in `sf org list` output"** — the alias/username/org id
  in `config.toml` doesn't match any locally-authenticated org. Re-run
  `sf org login web --alias <name>` or correct the config entry.
- **`INVALID_OPERATION_WITH_EXPIRED_PASSWORD` / auth errors mid-run** —
  the cached auth for that org has expired. Re-authenticate it and run
  again; orgs that already succeeded will be skipped naturally because
  `sf package install` is idempotent for the same version.
- **Long-running installs** — bump `wait` in the config (it's in minutes).
  Large managed packages routinely need 30+ minutes.
