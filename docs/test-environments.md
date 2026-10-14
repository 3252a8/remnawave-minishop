# Reusable test environments

Use `npm run check:local` for the full quality gate and `npm run qa:local` for
isolated live-panel and upgrade tests. Node 24, uv, Python 3.12 and Linux Docker
are required for the complete Windows gate. A successful unit suite with skips
is not the same as a successful zero-skips full stand.

## Storage and lifecycle

Python tools and npm dependencies are stored under the user cache directory,
outside the checkout. Keys include manifests, platform, architecture and Node
major version. A junction/symlink reconnects frontend dependencies after a clean.
Installations are marked ready only after success. Never cache a mutable test
database, `.env`, credentials, source snapshot, or a running service.

The `qa-deps` image contains only dependencies and tools, without product sources
or built frontend. `npm test` makes a new snapshot each time and removes it after
execution. Tests run in Linux storage with 4 CPU / 4 GiB limits by default.
`MINISHOP_TEST_CPUS`, `MINISHOP_TEST_MEMORY` and `MINISHOP_TEST_CACHE_DIR` allow
machine-specific budgets. An OOM is a failed gate; increase capacity explicitly
or serialize other builds rather than skipping tests.

Container commands have a two-hour deadline (`MINISHOP_TEST_TIMEOUT`, GNU timeout
syntax), then a 30-second kill grace. A killed host shell cannot leave a test
process running indefinitely. Full stands also cap each service at 2 CPU / 1 GiB
by default; database and Redis limits are 768 MiB and 256 MiB. Adjust
`MINISHOP_STAND_SERVICE_CPUS` / `MINISHOP_STAND_SERVICE_MEMORY` for application
services when needed. Preserve each run's separate databases and network.

Local bootstrap is serialized across checkouts; a complete gate holds a per-checkout
lease so generated files are not rebuilt concurrently by two local gates. A hard
host-process kill may leave a small lease file. The next run identifies its path
and dead owner: check that no gate remains active, then remove only that lease.
Do not steal a lease from a live process.

An unstarted `minishop-core-test-runtime-*` container holds the image. It has no
running process and consumes disk only. Cleanup must preserve
`minishop.local.keep=true` containers and named volumes still referenced by them:

```sh
docker container prune -f --filter "until=10m" --filter "label!=minishop.local.keep=true"
docker image prune -af --filter "until=24h"
docker volume prune -f
```

Do not run an unfiltered system/container prune on this engine. There is no Docker
label that can protect against an explicit forced removal or a factory reset.
The lock permits recovery from the registry after intentional cache removal.
Run `npm run test:env:gc` after accepting a new environment to release old keepers;
normal image pruning can then reclaim old layers. Retain the current native cache
and remove obsolete keys only when no checks use them. Git cleanup must stay within
the checkout and must never recurse into a linked dependency directory.

## Publication and refresh

GitLab publishes `docker.io/3252a8/remnawave-minishop-test-runtime` when dependency
inputs change on dev. The fingerprint covers the Docker recipe, Python manifests,
vendor repair script and platform. Publication produces a lock artifact with the
registry digest. Review and commit that artifact; consumption uses the digest,
never a moving latest tag. Dependency changes invalidate the old lock automatically.

`npm run test:env:refresh` refreshes pinned base-image packages and dependency
ranges locally; `node scripts/test_runtime.mjs publish` publishes explicitly and
writes the lock. Use Docker Hub authentication as `3252a8`. Review monthly and after
security advisories; bump pinned base digests when required. Do not rewrite an
accepted digest in place. Different architectures require their own matching lock
or build the exact recipe locally. An offline machine needs the current retained
image and dependency cache; first bootstrap needs network access.

A refresh prepares a candidate while ordinary runs keep using the accepted lock.
Validate a candidate with `MINISHOP_TEST_RUNTIME_CANDIDATE=1 npm run qa:local`
before publishing it. The publisher and its CI smoke tests use that same candidate.
Publication tags include the image identity as well as the recipe key, so a package
refresh does not move an older accepted registry tag. Source snapshots stream over
Docker stdin for pytest; the CI job does not require its filesystem to be mounted
inside a separate Docker daemon. The complete local Compose stand requires local
filesystem sharing with its Docker engine.

CI keeps all warnings, branch coverage, frontend assertions and the full panel
version matrix. Playwright uses two shards with one worker each in CI and two
workers locally; each full run starts a fresh demo server. Cache export failures
may be tolerated; build or test failures must remain fatal.

## Test execution costs

Vitest uses at most four workers, capped by the available CPU parallelism. Its
single Vite transform server can become the bottleneck with many workers. File
isolation, mock resets and the Svelte runes compiler stay enabled. Compare the
same suite with `npm --prefix frontend run test -- --maxWorkers=2` (or another
explicit limit) before changing the default on a different machine. Keep cold
module-cache timings separate from warm runs.

Facade contracts scan the current backend once per test module and reuse small
import indexes for independent assertions. Syntax trees are released per file;
malformed Python fails the check rather than silently escaping it.
Lifecycle notification DAL tests create only their four required tables, with a
new SQLite engine/database for each case and foreign keys enabled. These focused
tests do not replace migration, PostgreSQL, panel or upgrade coverage.

Import-isolation tests deliberately start fresh Python processes: reusing the
suite's interpreter would hide eager imports. Real Redis expiration tests retain
their clock waits, and browser tests retain independent contexts and fresh demo
builds. Do not trade these guarantees for a smaller duration number.

Redis fixtures close clients and remove their own keys in `finally`, including
after failed assertions. The ownership-loss case waits for real renewal to cancel
the old owner (bounded by ten seconds); its replacement owner does not expire
before the fencing assertion. Renewal beyond the original TTL is still tested
with a real elapsed-time wait.

The browser server supplies the complete, versioned install-guide configuration
from `frontend/e2e/fixtures/install-guides.json` to its fresh demo build. It never
downloads this external test input. See the fixture README for the upstream
revision and refresh procedure. Ordinary documentation builds still fetch the
upstream configuration, with three attempts and a 30-second deadline per attempt
that also covers the response body. A missing/malformed explicit fixture or an
exhausted download fails the build. `MINISHOP_DEMO_INSTALL_GUIDES_CONFIG` selects
an explicit local JSON file for a controlled build; there is no silent fallback.
