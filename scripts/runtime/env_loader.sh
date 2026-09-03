#!/usr/bin/env bash
# Purpose: Load .env into the process environment without executing it.
#
# Directory: scripts/runtime
# Dependencies: bash built-ins only
# Connection: sourced by start_backend.sh, start_everything.sh and the demo scripts
#
# The application reads secrets from os.environ. Nothing previously loaded .env, so a key
# written to the file was invisible to OpenTitanAdapter.from_project() and the Ethereum
# client, and the pipeline registered as unavailable at start-up with the key apparently
# set. That is finding C-56.
#
# `set -a && . ./.env` is NOT used. Sourcing executes the file as shell: a backtick, a
# $(...) or an unquoted # in any value would be executed or would truncate the value. A
# secrets file must not be executable by accident. Lines are parsed as KEY=VALUE and
# exported with the shell's own assignment, never through eval.
#
# WHAT THIS DOES NOT COVER. This loader affects only the scripts that source it. The
# following entry points still see no key and must be wired separately:
#
#   pytest                     -> tests/conftest.py
#   manage.py CLI              -> the module's entry point
#   scripts/demo/*.sh          -> source this file
#   wsgi.py under gunicorn     -> whichever unit or script launches it
#   python3 -c / -m, one-off   -> cannot be covered; export manually or use this loader
#   CI runners                 -> use the runner's secret store, never a committed .env
#
# Values are never printed. Failures name the variable and nothing else.

set -o nounset
set -o pipefail

SEMISECURE_ENV_FILE="${SEMISECURE_ENV_FILE:-.env}"

# Variable name and the minimum number of characters its value must have. The authoritative
# checks live in the application: OpenTitanAttestationVerifier rejects a key under 32 bytes
# after decoding, and the Ethereum client validates its own key. These minima only catch an
# empty or obviously truncated entry before the process starts.
SEMISECURE_REQUIRED_VARS=(
  "SEMISURE_OPENTITAN_VERIFICATION_KEY:32"
  "SEMISURE_PUF_MASTER_SECRET:32"
)

SEMISECURE_OPTIONAL_VARS=(
  "SEMISURE_ETHEREUM_PRIVATE_KEY"
)

semisecure_die() {
  printf 'FATAL: %s\n' "$1" >&2
  exit 1
}

semisecure_parse_env_file() {
  local file="$1"
  local line name value

  [ -f "$file" ] || semisecure_die "environment file not found: $file"

  while IFS= read -r line || [ -n "$line" ]; do
    # Skip blank lines and comments. A '#' inside a value is part of the value: only a
    # line whose first non-space character is '#' is a comment.
    case "${line#"${line%%[![:space:]]*}"}" in
      ''|'#'*) continue ;;
    esac

    name="${line%%=*}"
    value="${line#*=}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"

    # A line with no '=' is not an assignment.
    [ "$name" != "$line" ] || continue

    name="${name#"${name%%[![:space:]]*}"}"
    name="${name%"${name##*[![:space:]]}"}"
    name="${name#export }"

    # Reject anything that is not a plain variable name rather than exporting it.
    case "$name" in
      ''|*[!A-Za-z0-9_]*) continue ;;
    esac

    # Strip one matching pair of surrounding quotes. Inner characters are not interpreted.
    case "$value" in
      \"*\") value="${value#\"}"; value="${value%\"}" ;;
      \'*\') value="${value#\'}"; value="${value%\'}" ;;
    esac

    # Record that this name came from the file. semisecure_require_vars must not be
    # satisfied by a value inherited from the caller's environment: an inherited key is
    # not evidence that the file under validation is correct. That is finding C-61.
    SEMISECURE_ASSIGNED_NAMES="${SEMISECURE_ASSIGNED_NAMES:-} ${name}"

    # Assignment, not eval. The value is never expanded.
    export "${name}=${value}"
  done < "$file"
}

semisecure_require_vars() {
  local entry name minimum value missing=0

  for entry in "${SEMISECURE_REQUIRED_VARS[@]}"; do
    name="${entry%%:*}"
    minimum="${entry##*:}"
    value="${!name-}"

    case " ${SEMISECURE_ASSIGNED_NAMES:-} " in
      *" ${name} "*) : ;;
      *)
        printf 'FATAL: required environment variable is not assigned in the environment file: %s\n' "$name" >&2
        missing=1
        continue
        ;;
    esac

    if [ -z "$value" ]; then
      printf 'FATAL: required environment variable is not set: %s\n' "$name" >&2
      missing=1
      continue
    fi

    if [ "${#value}" -lt "$minimum" ]; then
      printf 'FATAL: environment variable is shorter than the required minimum: %s\n' "$name" >&2
      missing=1
    fi
  done

  [ "$missing" -eq 0 ] || exit 1
}

semisecure_report() {
  # Reporting only. Validation belongs to semisecure_require_vars, which has already run
  # and exited non-zero on any failure. A guard block was duplicated into this function by
  # a line-level patch; it printed a FATAL line for an optional variable absent from the
  # file and assigned to a variable local to the other function. Reporting must not fail,
  # and must not judge.
  #
  # Lengths only. No value, no prefix, no fragment is ever printed.
  local entry name value

  for entry in "${SEMISECURE_REQUIRED_VARS[@]}"; do
    name="${entry%%:*}"
    value="${!name-}"
    printf '%-40s set, %d characters\n' "$name" "${#value}"
  done

  for name in "${SEMISECURE_OPTIONAL_VARS[@]}"; do
    value="${!name-}"
    case " ${SEMISECURE_ASSIGNED_NAMES:-} " in
      *" ${name} "*)
        printf '%-40s set, %d characters\n' "$name" "${#value}"
        ;;
      *)
        printf '%-40s not set in the environment file\n' "$name"
        ;;
    esac
  done
}

semisecure_load_env() {
  semisecure_parse_env_file "$SEMISECURE_ENV_FILE"
  semisecure_require_vars
}

# Executed directly rather than sourced: load, report, exit. Reports lengths only.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  semisecure_load_env
  semisecure_report
fi
