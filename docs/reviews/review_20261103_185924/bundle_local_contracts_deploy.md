# bundle_local_contracts_deploy

## responsibilities

- Define the machine-readable contracts between CBrowser's services: two OpenAPI documents (public v1 and internal) and three protocol JSON Schemas (runtime agent, supervisor, stream).
- Define how the system is deployed: compose.yaml for the legacy single-container service, five Dockerfiles for the legacy and v2 runtime images, entrypoint scripts, and locked Python requirements per runtime.
- Provide the tooling that keeps contracts and assets honest: four schema export scripts, the Selkies vendoring script with its checksum manifest, the frontend dist verifier/build-stamp scripts, and the local gate runner run_gates.sh.
- Document deployment (DOCKER_DEPLOYMENT.md) and the environment template (.env.example, duplicated under config/).

## interfaces

- schemas/openapi/cbrowser_v1.json — public Manager API contract (4208 lines, read in full), including ProfileRuntimeResponse.
- schemas/openapi/cbrowser_internal.json — internal service API contract (5832 lines, read in full) with bearer security schemes serviceBearer / SupervisorServiceBearer / GatewayServiceBearer.
- schemas/runtime/agent_protocol.json, schemas/runtime/supervisor_protocol.json, schemas/stream/agent_protocol.json — JSON-Schema protocol contracts between supervisor, gateway, runtime agent, and stream components, exported as anyOf unions.
- Environment interface: .env.example / config/.env.example (AUTH_TOKEN, CBROWSER_PORT and related variables) consumed by compose.yaml.
- Image interfaces: five Dockerfiles (legacy + browser/stream/gateway/supervisor runtimes), two Dockerfile.dockerignore whitelists, and the selkies checksum manifest.

## dependencies

- compose.yaml depends on a host .env (from the .env.example templates) for AUTH_TOKEN and CBROWSER_PORT, and on a prebuilt src/frontend/dist/ that .gitignore excludes from the repo.
- The legacy Dockerfile depends on a pre-existing cbrowser:latest foundation image that nothing in this unit produces (see f_contracts_deploy_02).
- The supervisor/gateway Dockerfiles depend on per-directory Dockerfile.dockerignore whitelists staying in sync with their COPY lists.
- scripts/run_gates.sh depends on uv and on live package indexes for its unpinned --with dependencies (see f_contracts_deploy_06).
- The exported schemas depend on the export scripts being re-run when the source pydantic/FastAPI models change; nothing in this unit verifies freshness.

## flows

- Deploy (legacy): copy .env.example → .env, build frontend dist, `docker compose up --build` → config/docker/Dockerfile layers app code onto the foundation image → config/docker/entrypoint.sh starts the single service on container port 8080, published on loopback 56661 by default.
- Contract generation: source models → scripts/export_openapi.py / export_runtime_agent_protocol.py / export_stream_protocol.py / export_supervisor_protocol.py → schemas/openapi/*.json and schemas/{runtime,stream}/*.json (checked into the repo).
- Vendoring: scripts/vendor_selkies_web.py downloads the pinned Selkies wheel, verifies its SHA-256, extracts with path-traversal protection, and the result is checked against config/selkies/selkies_web_sha256.txt.
- Gating: scripts/run_gates.sh assembles throwaway uv environments and runs the contract/unit test selections without a project install.

## constraints

- Static review only: no image was built and no script was executed; build-failure findings rest on Dockerfile/dockerignore/compose text, which for f_contracts_deploy_01 and f_contracts_deploy_02 is deterministic.
- This unit covers contracts and deployment artifacts only; whether the application code enforces what these contracts promise (e.g. actual bearer checks, actual state enums) belongs to the backend units.
- Credential-like material exists only as template variables (notably the AUTH_TOKEN entry in .env.example / config/.env.example); only its location and kind are recorded, never a value — the templates contain placeholders, not live secrets.
- config/selkies/selkies_web_sha256.txt is a 2008-line generated checksum manifest; it was read in full but is treated as data, with its integrity role assessed via scripts/vendor_selkies_web.py.

## decisions

- compose.yaml's single service still deploys the legacy monolith (config/docker/Dockerfile + entrypoint.sh, port 8080 in-container) rather than the v2 runtimes.
- All v2 runtime base images are pinned by digest and their Python dependencies are fully locked via requirements.in → requirements.txt pairs.
- Internal service-to-service auth is specified as bearer tokens in the internal OpenAPI; user-facing auth for the legacy service is a single AUTH_TOKEN bearer/cookie.
- Selkies web assets are vendored with a pinned wheel SHA-256 and a per-file checksum manifest (config/selkies/selkies_web_sha256.txt) rather than fetched at deploy time.

## evidence

- compose.yaml:6,11,17 — image tag cbrowser:latest, loopback bind 127.0.0.1:${CBROWSER_PORT:-56661}:8080, AUTH_TOKEN injected with an empty-string default (interpolation form verified as `:-`, not `:?`).
- config/docker/supervisor_runtime/Dockerfile:18 COPYs launch_args.py; config/docker/supervisor_runtime/Dockerfile.dockerignore's whitelist omits it (full file read).
- config/docker/Dockerfile:2 `FROM cbrowser:latest` — same tag as the compose service image.
- .env.example and config/.env.example are byte-identical (26 lines each, identical MD5 f264a87c…); no root .dockerignore exists (verified by directory listing).
- schemas/openapi/cbrowser_internal.json: SupervisorServiceBearer and GatewayServiceBearer occur once each (definitions only); serviceBearer occurs 14 times (definition + all operation references).
- schemas/runtime/agent_protocol.json contains top-level "version": "2.0.0"; supervisor_protocol.json and schemas/stream/agent_protocol.json contain no version field.
- scripts/run_gates.sh:19-29 — uv run --with lines pin only cloakbrowser==0.6.4.
- Positive evidence: scripts/vendor_selkies_web.py verifies a pinned wheel SHA-256 and sanitizes zip paths (_safe_relative_path) before extraction; scripts/verify_frontend_dist.py validates dist against its manifest; config/docker/stream_runtime/entrypoint.sh enforces 0600 on secret files and fails fast.

## uncertainties

- Whether a deployment path for the v2 runtime images exists outside this unit (e.g. in docs or task files in other units) could not be checked from this unit's files alone; f_contracts_deploy_04 is stated for the deployment artifacts in this unit.
- Whether the supervisor genuinely requires root/NET_ADMIN (f_contracts_deploy_14) depends on its networking code, which lives in the backend units; the finding is marked suspected.
- Whether the checked-in schemas are byte-fresh against the current source models cannot be determined statically from this unit (the exporters were not run, per the static-review constraint); no freshness gate exists in run_gates.sh.
- DOCKER_DEPLOYMENT.md's KasmVNC/single-container description may describe an intentionally retained legacy path rather than pure staleness; the contradiction with compose.yaml's bind address stands either way.

## Findings

- [High][90] config/docker/supervisor_runtime/Dockerfile.dockerignore — Supervisor image build is broken: Dockerfile COPYs launch_args.py but its dockerignore whitelist excludes it
  - ID: f_contracts_deploy_01; verification: static
  - Evidence: config/docker/supervisor_runtime/Dockerfile:18 `COPY src/backend/cbrowser/launch_args.py /app/cbrowser/launch_args.py`.; config/docker/supervisor_runtime/Dockerfile.dockerignore starts with `**` (exclude everything) and its negation whitelist re-includes only __init__.py, secret_files.py, supervisor/*.py, domain/*.py, gateway/*.py, runtime_agent/*.py and config/docker/supervisor_runtime/requirements.txt — launch_args.py is never re-included, so it is absent from the build context and the COPY cannot succeed.; Contrast: config/docker/gateway_runtime/Dockerfile.dockerignore's whitelist matches its Dockerfile's COPY list exactly, showing the supervisor file is the outlier, not the pattern.
  - Impact: The supervisor runtime image cannot be built at all: the build fails at the launch_args.py COPY step. Any deployment or CI path that builds the v2 supervisor image is broken until the whitelist is fixed, and nothing in this unit (no CI build of the image) would have caught it.
  - Fix: Add `!src/backend/cbrowser/launch_args.py` to config/docker/supervisor_runtime/Dockerfile.dockerignore, and add a CI/local gate step that builds every runtime image (or at least checks each Dockerfile COPY source against its dockerignore whitelist) so this class of drift fails fast.

- [High][85] config/docker/Dockerfile:2 — Legacy production Dockerfile is self-referential: FROM cbrowser:latest is the same tag compose assigns to its own output
  - ID: f_contracts_deploy_02; verification: static
  - Evidence: config/docker/Dockerfile:1-2: comment 'Production image based on verified cbrowser foundation' followed by `FROM cbrowser:latest`.; compose.yaml:6 tags the service built from this Dockerfile as `image: cbrowser:latest` — the build output and the base image are the same tag.; There is no root .dockerignore and no other file in this unit that builds or publishes a distinct `cbrowser` foundation image for the FROM line to resolve against.
  - Impact: On a fresh machine `docker compose up --build` fails because cbrowser:latest does not exist yet; on a machine that already has an old cbrowser:latest, the build silently layers onto the stale previous build instead of the intended foundation, producing non-reproducible images whose contents depend on build history.
  - Fix: Point the legacy Dockerfile's FROM at a real, versioned base (e.g. the pinned python/debian foundation the other runtime Dockerfiles use, by digest), or rename the foundation image/tag so it cannot collide with the compose service image; document the bootstrap order if a two-stage build is intended.

- [Medium][90] .env.example:15 — AUTH_TOKEN defaults to empty (authentication disabled) while its own template comment calls it 'Required'
  - ID: f_contracts_deploy_03; verification: static
  - Evidence: .env.example:15 comment (credential variable, value not recorded): 'Required: bearer <kind: auth token> / cookie for the Manager. Blank disables authentication' — the same sentence calls the token required and says blank disables authentication entirely.; compose.yaml:17 injects the token with the `${AUTH_TOKEN:-}` form (empty-string default; verified the interpolation is `:-`, not the fail-fast `:?` form), so an unset host variable yields an empty token in the container.; compose.yaml:11 binds the port to 127.0.0.1 only, which limits exposure to the local host but does not restore authentication for any local process or port-forward scenario.
  - Impact: A deployer who follows the template and leaves the token blank gets a Manager with authentication fully disabled, while the comment's 'Required' wording gives false confidence that a token is in force. The loopback bind reduces but does not remove the risk (any local process, SSRF pivot, or user-added port mapping reaches an unauthenticated control plane).
  - Fix: Make compose fail fast when the token is unset (e.g. `${AUTH_TOKEN:?AUTH_TOKEN must be set}`), and rewrite the .env.example comment to state one consistent rule: token required, blank is rejected — or, if unauthenticated local mode is intentional, say so plainly and drop the word 'Required'.

- [Medium][80] compose.yaml — Four v2 runtime images have no deployment path: compose.yaml never references them
  - ID: f_contracts_deploy_04; verification: static
  - Evidence: compose.yaml defines exactly one service (the legacy image from config/docker/Dockerfile, image cbrowser:latest, port 127.0.0.1:${CBROWSER_PORT:-56661}:8080).; No service in compose.yaml references config/docker/browser_runtime/Dockerfile, config/docker/stream_runtime/Dockerfile, config/docker/gateway_runtime/Dockerfile, or config/docker/supervisor_runtime/Dockerfile, and no other file in this unit (DOCKER_DEPLOYMENT.md, scripts/*) builds or runs them.
  - Impact: Within the deployment surface this unit defines, the entire v2 multi-runtime topology (browser/stream/gateway/supervisor) is unbuildable-as-a-system: the images exist and the protocol schemas describe them talking to each other, but there is no declared way to run them together. Operators following the repo's deployment artifacts get only the legacy single container.
  - Fix: Either add compose services (or a documented compose profile / build script) for the four v2 runtime images, or mark the runtime Dockerfiles as not-yet-deployable in DOCKER_DEPLOYMENT.md so readers do not assume a working multi-service deployment exists.

- [Medium][85] DOCKER_DEPLOYMENT.md — DOCKER_DEPLOYMENT.md contradicts the actual deployment: bind address, exposure, prerequisites, and architecture are all stale
  - ID: f_contracts_deploy_05; verification: static
  - Evidence: DOCKER_DEPLOYMENT.md describes the host port as reachable on 0.0.0.0:56661 / LAN-accessible and the deployment as a single container bundling Xvfb/KasmVNC; compose.yaml:11 actually binds 127.0.0.1:${CBROWSER_PORT:-56661} (loopback only, configurable port).; .gitignore ignores src/frontend/dist/, and scripts/verify_frontend_dist.py exists because the legacy image build needs a prebuilt dist with a manifest — but DOCKER_DEPLOYMENT.md's quick-start is just `docker compose up --build` with no frontend build or vendor step, so a fresh clone following the doc fails.; DOCKER_DEPLOYMENT.md never mentions the v2 runtime images, the Selkies WebRTC stack (config/selkies/, config/docker/*_runtime/), or the vendoring script scripts/vendor_selkies_web.py.
  - Impact: The only deployment document in the repo misstates the network exposure (in the alarming direction — it claims LAN exposure that the config no longer has, and omits the auth-token caveat), omits a build prerequisite that makes the documented quick-start fail on a fresh clone, and documents an architecture (single-container KasmVNC) that the config tree has moved beyond.
  - Fix: Rewrite DOCKER_DEPLOYMENT.md against the current compose.yaml: loopback bind and CBROWSER_PORT, the required frontend build step before image build, the AUTH_TOKEN requirement, and a section stating the v2 runtimes' deployment status.

- [Medium][90] scripts/run_gates.sh:19 — run_gates.sh assembles its test environment from unpinned packages, so the local gate is not reproducible
  - ID: f_contracts_deploy_06; verification: static
  - Evidence: scripts/run_gates.sh:19-29 builds each gate environment ad hoc with `uv run --no-project --python ">=3.12" --with pytest --with pytest-asyncio --with fastapi --with pydantic --with httpx --with websockets ...` — none of pytest, fastapi, pydantic, httpx, sqlalchemy, alembic, uvicorn, etc. carries a version constraint.; The single pinned dependency in the whole script is `cloakbrowser==0.6.4` (run_gates.sh:22 and :27), proving pinning was possible and applied selectively.; Contrast with the runtime images in this same unit, whose requirements.txt files are fully hash/version locked — the gate environment is held to a weaker standard than the artifacts it gates.
  - Impact: Gate results are not reproducible over time: an upstream release of pytest, fastapi, or pydantic can change gate behaviour or break the gate environment itself, so a red gate may mean 'the internet changed' rather than 'the code regressed', and a green gate today does not certify the same environment tomorrow.
  - Fix: Pin the gate environment: commit a lockfile (e.g. uv lock / a requirements file with exact versions) for each gate invocation in run_gates.sh, or run the gates inside the already-locked runtime environments.

- [Low][75] schemas/runtime/supervisor_protocol.json — Exported protocol schemas are undiscriminated anyOf unions, so validation cannot distinguish message types
  - ID: f_contracts_deploy_07; verification: static
  - Evidence: scripts/export_supervisor_protocol.py (and the sibling exporters) generate schemas/runtime/supervisor_protocol.json as a flat anyOf union of all message models with no discriminator field.; In schemas/runtime/supervisor_protocol.json, ResetBlockedRequest carries only profile_id — a payload that also satisfies ProfileRuntimeStatus-shaped and StartProfileRequest-shaped members of the union, so schema validation alone cannot determine which message type a payload is.; The same anyOf-union shape is used in schemas/runtime/agent_protocol.json and schemas/stream/agent_protocol.json.
  - Impact: Consumers validating protocol messages against these exported schemas get weaker guarantees than the pydantic models provide in-process: structurally ambiguous payloads validate against the wrong message type, so the exported contract cannot catch misrouted or malformed messages at a service boundary.
  - Fix: Add a discriminating field (e.g. a required literal `type`/`kind` per message) or export per-message schemas keyed by message name, so validators can reject cross-type payloads instead of accepting anything matching any member.

- [Low][90] schemas/runtime/supervisor_protocol.json — Protocol schema versioning is inconsistent: runtime agent schema has a version field, supervisor and stream schemas have none
  - ID: f_contracts_deploy_08; verification: static
  - Evidence: schemas/runtime/agent_protocol.json top level contains `"version": "2.0.0"` (verified by grep).; The same grep finds no version field at the top level of schemas/runtime/supervisor_protocol.json or schemas/stream/agent_protocol.json — the three exporters (scripts/export_runtime_agent_protocol.py, export_supervisor_protocol.py, export_stream_protocol.py) do not emit a consistent envelope.
  - Impact: Tooling that versions or negotiates protocol compatibility cannot treat the three exported contracts uniformly: one carries a version, two carry none, so consumers must special-case which schema they are reading before they can even check compatibility.
  - Fix: Make all three protocol exporters emit the same top-level envelope (including a version field sourced from the same constant), and regenerate the three schema files.

- [Low][95] schemas/openapi/cbrowser_internal.json — Internal OpenAPI defines per-service bearer schemes that nothing uses: all operations collapse to one generic serviceBearer
  - ID: f_contracts_deploy_09; verification: static
  - Evidence: schemas/openapi/cbrowser_internal.json defines three bearer security schemes in components: serviceBearer, SupervisorServiceBearer, and GatewayServiceBearer (one occurrence each — their definitions).; All 14 security references across the internal operations point at the generic serviceBearer; SupervisorServiceBearer and GatewayServiceBearer are referenced zero times (verified by counting occurrences in the file).
  - Impact: The internal API contract suggests per-service credentials (a supervisor token distinct from a gateway token), but as exported, any holder of the single generic service bearer satisfies every internal operation — the contract overstates the identity separation that actually exists, and generated clients/servers will not enforce per-service identity.
  - Fix: Either wire each internal operation to the scheme matching the service identity it expects (supervisor vs gateway), or delete the two unused schemes so the contract honestly states that one shared bearer identity is used.

- [Low][80] schemas/openapi/cbrowser_v1.json — v1 OpenAPI leaves profile runtime states as bare strings while the supervisor protocol enums the same fields
  - ID: f_contracts_deploy_10; verification: static
  - Evidence: In schemas/openapi/cbrowser_v1.json, ProfileRuntimeResponse's desired_state and observed_state are plain strings with no enum constraint.; schemas/runtime/supervisor_protocol.json models the same lifecycle states as enums for the supervisor protocol, so the vocabulary exists in the contract set but is not applied at the v1 API surface.
  - Impact: v1 API consumers cannot rely on a closed set of runtime states: any string is contract-valid, so client code must defensively handle unknown states that the internal protocol would have rejected, and state-vocabulary drift between the API and the supervisor protocol will not be caught by schema checks.
  - Fix: Export desired_state/observed_state in cbrowser_v1.json with the same enum used by the supervisor protocol (generated from the shared model), so v1 clients get the closed state vocabulary.

- [Low][95] .env.example — Environment template is duplicated byte-for-byte at repo root and config/ with no sync mechanism
  - ID: f_contracts_deploy_11; verification: static
  - Evidence: .env.example and config/.env.example are byte-identical today: both 26 lines, identical MD5 (f264a87c…) — verified by checksum, not just visual comparison.; Nothing in this unit (no script in scripts/, no gate in run_gates.sh) checks that the two copies stay in sync.
  - Impact: Two independently editable copies of the environment template will eventually drift: a variable added or a warning edited in one copy silently fails to reach users of the other, and the AUTH_TOKEN wording (see f_contracts_deploy_03) is exactly the kind of text that gets fixed in one place only.
  - Fix: Keep one canonical template and generate or symlink the other, or add a trivial equality check to run_gates.sh; alternatively document which copy each consumer reads and delete the unused one.

- [Low][85] config/docker/stream_runtime/Dockerfile — Stream runtime production image ships a full build toolchain and -dev packages
  - ID: f_contracts_deploy_12; verification: static
  - Evidence: config/docker/stream_runtime/Dockerfile installs build-essential and multiple -dev packages into the final (only) stage — there is no multi-stage split separating build tooling from the runtime image.; The same Dockerfile both uses an apt cache mount and runs `rm -rf /var/lib/apt/lists/*`, a belt-and-braces combination that suggests the layer hygiene was not thought through.; Contrast: the browser/gateway/supervisor runtime Dockerfiles in this unit do not carry a compiler toolchain in the final image.
  - Impact: The production stream image is larger and carries a full compiler toolchain and development headers — unnecessary attack surface (a compromised service can compile exploit code in-place) and slower pulls/deploys for every stream instance.
  - Fix: Split the stream image into a builder stage (toolchain + -dev packages, compile native deps into wheels) and a runtime stage that copies only the built artifacts and runtime libraries.

- [Info][90] config/docker/stream_runtime/requirements.txt — Cross-image dependency drift: stream runtime pins a different pydantic patch version than the other three runtimes
  - ID: f_contracts_deploy_13; verification: static
  - Evidence: config/docker/stream_runtime/requirements.txt pins pydantic 2.14.1 / pydantic-core 2.50.1, while config/docker/browser_runtime/requirements.txt, gateway_runtime/requirements.txt, and supervisor_runtime/requirements.txt pin pydantic 2.14.2 / pydantic-core 2.50.2 (compared across the four locked files in this unit).; All four images exchange the protocol messages defined by the schemas in this unit, so serialization behaviour is a cross-image concern.
  - Impact: Minor today (a patch-level difference), but the services validate and serialize the same protocol payloads with different pydantic builds; edge-case validation/serialization differences would surface as cross-service inconsistencies that are hard to attribute. It also signals the four lockfiles are regenerated independently with no shared constraint.
  - Fix: Regenerate the stream runtime lockfile so all four runtimes share the same pydantic/pydantic-core versions, and consider a single shared constraints file for the common dependencies.

- [Info][70] config/docker/supervisor_runtime/Dockerfile — Supervisor runtime image runs as root with no USER directive and no documented privilege rationale
  - ID: f_contracts_deploy_14; verification: suspected
  - Evidence: config/docker/supervisor_runtime/Dockerfile has no USER directive (verified: no USER line in the file) and installs iptables, which typically implies the container is expected to hold NET_ADMIN and/or a Docker socket — a privileged posture that no file in this unit documents or justifies.; The sibling runtime Dockerfiles in this unit do drop privileges / define their runtime user explicitly, making the supervisor the outlier.
  - Impact: The most privileged component in the topology (it supervises other containers and manipulates networking) runs as root by default with its privilege needs undocumented; deployers cannot apply least-privilege settings, and a supervisor compromise is immediately a root compromise inside its container.
  - Fix: Document the supervisor's privilege requirements (capabilities, socket mounts) in DOCKER_DEPLOYMENT.md and the Dockerfile, and if full root is not required, run as a dedicated user with only the needed capabilities granted by the (future) compose service.

- [Info][70] config/docker/browser_runtime/Dockerfile — Browser runtime's default CMD asks for --help but its entrypoint rejects unknown arguments with exit 1
  - ID: f_contracts_deploy_15; verification: static
  - Evidence: config/docker/browser_runtime/Dockerfile sets the default command to `--help` (CMD ["--help"]).; config/docker/browser_runtime/entrypoint.sh dispatches on its arguments and exits 1 on unrecognized input rather than printing usage — so the image's own default invocation takes the error path.
  - Impact: Running the browser runtime image with no arguments — the natural smoke test for a freshly built image — exits non-zero and looks like a broken image, wasting operator time and potentially failing naive deployment health checks that start the container bare.
  - Fix: Make the entrypoint handle --help/-h explicitly by printing usage and exiting 0, or change the default CMD to a real no-op/health invocation that the entrypoint accepts.

- [Info][95] scripts/export_openapi.py — export_openapi.py omits the trailing newline that the other three export scripts all write
  - ID: f_contracts_deploy_16; verification: static
  - Evidence: scripts/export_openapi.py writes the JSON payload without appending a trailing newline.; scripts/export_runtime_agent_protocol.py, scripts/export_stream_protocol.py, and scripts/export_supervisor_protocol.py each append "\n" to their output — four sibling exporters, two conventions.
  - Impact: Trivial but real: generated files that lack a trailing newline produce noisy diffs and trip POSIX-text-file linters/formatters, and the inconsistency means a future repo-wide format gate will flag one exporter or the other unpredictably.
  - Fix: Align export_openapi.py with the other exporters (append the trailing newline) and regenerate schemas/openapi/*.json.

## views

```json
{
  "contracts": {
    "reviewer": "f1da787b-2302-489c-8788-76ed1fe1ee7f",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "f1da787b-2302-489c-8788-76ed1fe1ee7f",
    "status": "completed"
  },
  "design": {
    "reviewer": "f1da787b-2302-489c-8788-76ed1fe1ee7f",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "f1da787b-2302-489c-8788-76ed1fe1ee7f",
    "status": "completed"
  },
  "performance": {
    "reviewer": "f1da787b-2302-489c-8788-76ed1fe1ee7f",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "f1da787b-2302-489c-8788-76ed1fe1ee7f",
    "status": "completed"
  },
  "security": {
    "reviewer": "f1da787b-2302-489c-8788-76ed1fe1ee7f",
    "status": "completed"
  },
  "tests": {
    "reviewer": "f1da787b-2302-489c-8788-76ed1fe1ee7f",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  ".env.example",
  ".gitattributes",
  ".gitignore",
  ".prettierignore",
  "DOCKER_DEPLOYMENT.md",
  "compose.yaml",
  "config/.env.example",
  "config/docker/Dockerfile",
  "config/docker/browser_runtime/Dockerfile",
  "config/docker/browser_runtime/entrypoint.sh",
  "config/docker/browser_runtime/requirements.in",
  "config/docker/browser_runtime/requirements.txt",
  "config/docker/entrypoint.sh",
  "config/docker/gateway_runtime/Dockerfile",
  "config/docker/gateway_runtime/Dockerfile.dockerignore",
  "config/docker/gateway_runtime/requirements.in",
  "config/docker/gateway_runtime/requirements.txt",
  "config/docker/stream_runtime/Dockerfile",
  "config/docker/stream_runtime/entrypoint.sh",
  "config/docker/stream_runtime/requirements.in",
  "config/docker/stream_runtime/requirements.txt",
  "config/docker/supervisor_runtime/Dockerfile",
  "config/docker/supervisor_runtime/Dockerfile.dockerignore",
  "config/docker/supervisor_runtime/requirements.in",
  "config/docker/supervisor_runtime/requirements.txt",
  "config/selkies/selkies_web_sha256.txt",
  "schemas/openapi/cbrowser_internal.json",
  "schemas/openapi/cbrowser_v1.json",
  "schemas/runtime/agent_protocol.json",
  "schemas/runtime/supervisor_protocol.json",
  "schemas/stream/agent_protocol.json",
  "scripts/export_openapi.py",
  "scripts/export_runtime_agent_protocol.py",
  "scripts/export_stream_protocol.py",
  "scripts/export_supervisor_protocol.py",
  "scripts/run_gates.sh",
  "scripts/vendor_selkies_web.py",
  "scripts/verify_frontend_dist.py",
  "scripts/write_frontend_build_stamp.py"
]
```
