# NVM Loader Cartridge

Use an existing [NVM installation](https://github.com/nvm-sh/nvm) from Bash Commander, with optional user-owned command links after `nvmh use`. This cartridge does not install NVM or Node.js, edit shell profiles, or require `sudo`.

**Prerelease policy:** Bash Commander is an official OAS FOSS project
preparing its first public prerelease. Support will cover only exact configurations
and flows that pass final release acceptance. The current native baseline is Linux
Mint 22.3/x86_64/Bash 5.2.21, with a private historical Bash 4.3 compatibility
case; other platforms remain unverified portability targets. This is a Bash-centric
core without a global Linux or `sudo` requirement. A language-feature threshold
does not certify a platform or every upstream runtime version. Final release
acceptance and public availability are still pending.

The examples require matching Console/cartridge revisions made available for
review or publication; a default-branch checkout may not contain these changes.
See the matching Console's [prerelease support policy](https://github.com/bashcmdr/console/blob/main/docs/SUPPORT.md)
for the exact evidence boundaries, working flows and unavailable features.


## Requirements

- The selected [Bash Commander console](https://github.com/bashcmdr/console), including its Bash 4.3+ interpreter requirement. The console uses namerefs; the cartridge's associative arrays alone do not establish a lower supported console version.
- A readable, nonempty `nvm.sh` in `NVM_DIR`, normally `$HOME/.nvm`, to activate NVM. Install NVM separately using its [upstream instructions](https://github.com/nvm-sh/nvm#installing-and-updating), reviewing its installer and shell-profile changes before running them.
- Existing Node.js versions installed through NVM for version switching. No system-wide Node.js installation is required by the cartridge.
- Git and `jq` for the console installation workflow below. Runtime commands and link operations also need ordinary shell tools such as `dirname`, `cat`, `readlink`, `mkdir`, `ln`, `rm` and `rmdir`.
- A real, writable directory owned by the current user for link synchronization, normally `$HOME/.local/bin`.

No Pyenv or other cartridge is required. Use absolute Bash paths for configuration, including mounted paths where appropriate; native Windows path strings are not accepted as `NVM_DIR`. Upstream NVM compatibility is a separate prerequisite. Local regressions use Linux host Bash and a private Bash 4.3 build; they do not certify Git Bash, OpenWrt, Termux, or other native platforms.

## Install and enable

These commands use the canonical `bashcmdr` executable. `bcm` is an optional shortcut when it resolves to that installation. A registry is not needed for this explicit Git-source workflow. Run the clone into a new destination; if a console is already installed, use its selected root rather than cloning over it.

```bash
git clone https://github.com/bashcmdr/console.git "$HOME/.local/bin/bashcmdr"
export BASHCMDR_ROOT_DIR="$HOME/.local/bin/bashcmdr"
export PATH="$BASHCMDR_ROOT_DIR/bin:$PATH"
bashcmdr version
bashcmdr cartridge install nvm-loader --from https://github.com/bashcmdr/cartridge-nvm.git
bashcmdr cartridge plug nvm-loader
bashcmdr cartridge list active
```

`plug` records activation state and runs the callback in the command's process. An external executable cannot export NVM functions or environment changes into its parent shell. To load the marked-active cartridge in your current shell, start a fresh Bash process and initialize that console there:

```bash
export BASHCMDR_ROOT_DIR="$HOME/.local/bin/bashcmdr"
export PATH="$BASHCMDR_ROOT_DIR/bin:$PATH"
source "$BASHCMDR_ROOT_DIR/boot/shell-init.bashcmdr"
printf 'Bash Commander boot status: %s\n' "$BASHCMDR_BOOT_EXIT_CODE"
nvm --version
```

The reported boot status must be `0` before continuing. Sourcing the initializer is deliberately nonfatal, so its return status alone does not establish successful boot. Initialization runs once per shell; open a fresh shell after correcting a failed boot or changing installations. Make persistent profile changes yourself only after verifying this initialization path.

For an NVM installation outside `$HOME/.nvm`, export `NVM_DIR` to its absolute Bash path before initialization. An unset or empty value uses the default. A nonempty caller value is retained, and configuration is read again on each activation.

## Use installed Node versions

After successful shell initialization, `nvm` is a shell function. Use NVM's own instructions to install the desired Node versions first; `--lts` below selects an already-installed LTS version.

```bash
nvm list
nvm use --lts
nvmh use --lts
node --version
```

`nvm use` changes the calling shell's selected version without synchronizing shared links. `nvmh use` delegates the same arguments to NVM and, only after a successful switch, synchronizes executable links in the user-owned directory. Other `nvmh` actions pass through to NVM without the link hook.

The hook uses `$BASHCMDR_NVM_LINK_DIR` when nonempty, otherwise `$HOME/.local/bin`. Set it before switching if another user-owned directory is needed. Add that directory to the relevant process's PATH yourself. Existing NVM shells may still find their own version directory first; shared links are not a way to change every shell's environment.

The hook checks the selected NVM version and executable files, preserves foreign files and symlinks, and removes only recognized stale links into this NVM installation. A conflicting name, lock, or link failure makes `nvmh use` fail even if NVM has already switched versions. Some recognized links may have changed before a later filesystem failure; inspect and retry after resolving it. A stale `.bashcmdr-nvm.lock` requires inspection before removal, not blind deletion.

No passwordless-sudo rule or system-directory write is needed. System bin directories are unsupported as the link destination. The hook does not run arbitrary custom post-use commands.

## Deactivate

```bash
bashcmdr cartridge unplug nvm-loader
nvm_deactivate
```

The external `unplug` changes persistent state for future startup and deactivates its own command process. The second command is available after activation and asks NVM to deactivate in the current shell. It clears the cartridge's loaded marker only on success, while retaining `NVM_DIR`, NVM functions/helpers, completion definitions and shared user-local links. It does not implicitly run `nvm unload`, erase NVM data or reverse arbitrary upstream script effects.

## Diagnose and get help

```bash
bashcmdr help cartridge
nvm_help
bashcmdr cartridge diagnose nvm-loader
nvm_diagnose
nvm --version
bashcmdr console log --lines 50
```

The console's help command shows cartridge-management usage; `nvm_help` shows this cartridge's own help after it has been loaded. The external diagnostic checks its own process, so it may report that the NVM function is not loaded even when the parent shell has it. `nvm_diagnose` inspects the function in the current initialized shell. Diagnosis reports configured file presence, checked NVM version/list queries when loaded, optional completion presence and the proposed link directory; it does not certify successful sourcing or every NVM feature. It does not run Node.js or npm.

Use `nvm --version` on the loaded function, not `nvm.sh --version`: `nvm.sh` is a script to source. Use `bashcmdr console log` for the selected installation's operation log rather than constructing a path from a cartridge-local variable. Review logs before sharing them.

In a bare cartridge checkout, these commands inspect existing configuration without requiring installed console libraries:

```bash
bash main.bashcmdr help
bash main.bashcmdr setup
bash main.bashcmdr diagnose
```

`setup` reports presence without certifying activation; a missing installation is dormant success, while an existing directory with an unusable script fails. Diagnosis returns nonzero for missing/invalid inputs. Sourcing `main.bashcmdr` defines functions; even `source main.bashcmdr activate` does not dispatch activation. Use console initialization for current-shell activation. Standalone activation requires the console guard and is not a bare-checkout installation method.

## Failure behavior

Activation re-sources the selected `nvm.sh`, checks its status, verifies the `nvm` function and a nonempty version result, then loads a readable optional completion file. It sets `BASHCMDR_NVM_LOADED=1` only after those steps succeed. Exported markers do not replace initialization in a child shell. A missing installation remains dormant without a loaded marker; malformed configuration and failed sourcing/probes return failure. Trusted upstream scripts may leave partial effects on failure.

The link hook returns `1` for unavailable NVM, an invalid/conflicting destination, lock or link-operation failure; `2` when no valid NVM-managed version is active; and `127` when that version has no executable files. NVM failures are propagated. Treat a nonzero `nvmh` result as failure even if the version switch itself succeeded.

## Containers and development

Noninteractive containers need Bash and explicit initialization in each process that needs NVM. Cloning the console alone does not install this cartridge, and separate build steps do not share shell functions. Apply the installation and initialization flow above to the process that runs Node; consult [NVM's container guidance](https://github.com/nvm-sh/nvm#installing-in-docker) for its installer. This guide does not claim a verified container image or Dockerfile.

```bash
python3 tests/test_runtime_context.py
python3 tests/test_nvm_hook.py
python3 tests/test_docs.py --console-root /absolute/path/to/bashcmdr-console
bash -n main.bashcmdr
shellcheck -x main.bashcmdr
```

Tests use temporary homes, inert upstream/tool interfaces and owned local Git repositories. They do not install upstream NVM/Node, alter a live console or establish public accessibility.

The shared development payload runs shell syntax checks, manifest parsing and
the three Python suites above, recording tool identities, individual exit
statuses, full stdout/stderr and owned runtime/guide records:

```bash
bash --noprofile --norc tests/ci.bash /absolute/path/to/bashcmdr-console
```

The private workflow proposal replaces inherited calls to missing Console test
scripts with these required cartridge tests. A failed check stops the payload;
diagnostic artifacts are retained even after failure. The workflow proposes
Ubuntu 24.04 and the Python 3.14 series as a development baseline, with exact
action commit references and a fixed Console compatibility input. It checks
for Bash 4.3+, Git and jq without assuming sudo or installing distro packages.
The action implementations use Node 24 and require a compatible Actions runner
(at least 2.327.1); this hosted runner proposal is separate from using the
cartridge. See the official [checkout](https://github.com/actions/checkout),
[setup-python](https://github.com/actions/setup-python) and
[artifact](https://github.com/actions/upload-artifact) documentation.

This private proposal has not run on GitHub. Its pinned Console commit must
become accessible to the workflow before hosted execution can succeed. The
release platform matrix, actual hosted results and release acceptance remain
pending. An Ubuntu development runner does not limit the Bash-centric runtime
contract or certify Windows, Termux, OpenWrt or other native systems. The tests
use owned NVM/Node interfaces and do not acquire or configure a real toolchain.

## Project links and licensing

- [Bash Commander console](https://github.com/bashcmdr/console)
- [This cartridge](https://github.com/bashcmdr/cartridge-nvm)
- [Upstream NVM](https://github.com/nvm-sh/nvm)

Copyright 2026 Eric Milgram. Original project code is licensed under [Apache-2.0](LICENSE); see [NOTICE](NOTICE). Bash Commander is an official OAS FOSS project.

Upstream NVM documents its own licensing separately. No production-readiness or release promise follows from fixture test results.

## Manifest metadata

The `lifecycle` entries name Bash functions defined by sourcing `main.bashcmdr`;
use them in the shell context described above. They are not executable file paths
or commands evaluated by the Console from this metadata. `testing.test_script`
names the development entrypoint `tests/ci.bash`, which takes the compatible
Console checkout argument shown above. Tests are not run automatically when this
cartridge is sourced or activated. External dependency entries are discovery
hints; the runtime selection rules above determine the tools actually used.
Console dependency and loaded-state checks are separate from these descriptive
lifecycle/testing entries.
