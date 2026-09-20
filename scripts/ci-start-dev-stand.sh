#!/usr/bin/env bash
set -uo pipefail

max_attempts="${DEV_STAND_START_ATTEMPTS:-3}"
base_delay_seconds="${DEV_STAND_START_DELAY_SECONDS:-10}"

case "$max_attempts" in
  ''|*[!0-9]*|0) echo "DEV_STAND_START_ATTEMPTS must be a positive integer" >&2; exit 2 ;;
esac
case "$base_delay_seconds" in
  ''|*[!0-9]*) echo "DEV_STAND_START_DELAY_SECONDS must be a non-negative integer" >&2; exit 2 ;;
esac

transient_pattern='rpc error:.*(Unavailable|EOF)|failed to receive status|unexpected EOF|connection reset by peer|TLS handshake timeout|i/o timeout|context deadline exceeded|wget .*did not complete successfully: exit code: 4|(^|[^0-9])(502|503|504)([^0-9]|$)'
log_file="$(mktemp)"
trap 'rm -f "$log_file"' EXIT

for ((attempt = 1; attempt <= max_attempts; attempt += 1)); do
  : > "$log_file"
  npm run dev:stand:up 2>&1 | tee "$log_file"
  exit_code="${PIPESTATUS[0]}"

  if [ "$exit_code" -eq 0 ]; then
    exit 0
  fi

  if ! grep -Eiq "$transient_pattern" "$log_file"; then
    echo "Dev stand startup failed with a non-transient error; not retrying." >&2
    exit "$exit_code"
  fi

  if [ "$attempt" -eq "$max_attempts" ]; then
    echo "Dev stand startup still failed after $max_attempts transient attempts." >&2
    exit "$exit_code"
  fi

  delay_seconds=$((base_delay_seconds * attempt))
  echo "::warning title=Transient dev stand startup failure::Attempt ${attempt}/${max_attempts} failed; cleaning up and retrying in ${delay_seconds}s."
  npm run dev:stand:down || true
  sleep "$delay_seconds"
done
