#!/usr/bin/env bash
# Shared local/CI payload. External NVM/Node interfaces remain owned test doubles.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
results="$root/tests/results/ci"
mkdir -p "$results"

run() {
    local label=$1 status=0
    shift
    "$@" >"$results/$label.stdout.log" 2>"$results/$label.stderr.log" || status=$?
    printf '%s\n' "$status" >"$results/$label.exit"
    cat "$results/$label.stdout.log"
    cat "$results/$label.stderr.log" >&2
    return "$status"
}

# Keep preflight failures in the same evidence directory as test failures.
run capabilities bash --noprofile --norc -c '
    set -euo pipefail
    for tool in bash python3 git jq env; do command -v "$tool"; done
    [[ ${BASH_VERSINFO[0]} -gt 4 || ( ${BASH_VERSINFO[0]} -eq 4 && ${BASH_VERSINFO[1]} -ge 3 ) ]]
'
run tool-identities python3 - "$results/tool-identities.json" <<'PY'
import hashlib, json, pathlib, platform, shutil, subprocess, sys
tools = {}
for name, args in [('bash',['--version']),('python3',['--version']),('git',['--version']),('jq',['--version'])]:
    path = pathlib.Path(shutil.which(name)).resolve()
    tools[name] = {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                   'version':subprocess.check_output([str(path),*args],text=True).splitlines()[0]}
pathlib.Path(sys.argv[1]).write_text(json.dumps({'tools':tools,'platform':platform.platform(),
    'scope':'Development runner with owned NVM/Node interfaces; no native alternate-platform or release support certification.'},indent=2)+'\n')
PY
run console-input bash --noprofile --norc -c '
    set -euo pipefail
    [[ $# == 1 && -d $1/bin && -d $1/lib && -d $1/boot && -f $1/VERSION ]]
' bash "${1-}"
console=$(cd "$1" && pwd)
for file in main.bashcmdr tests/ci.bash; do
    run "syntax-${file//\//-}" bash -n "$file"
done
run manifest jq -e 'type == "object"' manifest.json
run runtime env NVM_RUNTIME_TEST_EVIDENCE_DIR="$results/runtime-records" python3 tests/test_runtime_context.py
run hooks python3 tests/test_nvm_hook.py
run guide env NVM_DOCS_TEST_EVIDENCE_DIR="$results/guide-records" python3 tests/test_docs.py --console-root "$console"
printf '%s\n' 'All development checks passed.'
