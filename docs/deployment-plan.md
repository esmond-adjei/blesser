# Deployment implementation plan

Prepared 2026-11-21. Proposed, awaiting approval. This plan covers Graduator on OVH AMD64 and Blesser on Oracle ARM64, each with its own self-hosted Coolify. The two repositories carry the same initial coordination plan. Each repository owns its application configuration and action log.

See [this application’s audit](deployment-audit.md) and [action log](deployment-actions.tsv). No provisioning, installation, firewall change, production deployment or DNS change is authorized by this document.

## Proposed architecture

- Each server runs Ubuntu LTS, Docker, its own Coolify and proxy, PostgreSQL 16, one API process and one worker process. Coolify state and credentials are independent.
- Graduator adds the member Nginx app and a static marketing-site container. Blesser adds member and admin Nginx apps, the Astro server and the existing public edge routing.
- Only the proxy publishes application HTTP ports. Database, API, worker and internal site ports remain private. Application port 8000 must not collide with Coolify’s dashboard port 8000 on the host.
- Build release images in GitHub Actions, publish AMD64 and ARM64 manifests, then let Coolify pull the approved immutable release. Avoid compiling application images on these budget production servers.
- Keep app PostgreSQL and upload volumes separate from Coolify’s own database, cache and state. Do not make either application depend on the other server for normal operation.
- Keep initial API replica count at one. Tune worker concurrency from a conservative starting value of two per application after measurement. Do not add Redis or local model serving without a demonstrated need.

Coolify supports both architectures and lists minimum hardware of two cores, 2 GB RAM and 10 GB free disk. Those are platform minimums, not measured requirements for these applications. Allow capacity for PostgreSQL, workers, files, images and temporary restores. [Coolify installation requirements](https://coolify.io/docs/get-started/installation)

Use the Git repository Compose deployment path. Coolify can inject referenced environment variables and route a domain to a receiving service’s internal port. Inspect the rendered Compose and actual persistent-volume names before loading data. [Coolify Compose documentation](https://coolify.io/docs/applications/builds/docker-compose)

## Budget and provider constraints

The recurring infrastructure ceiling is GH₵200 per month. The figures below are proposed spending allocations, not invoices or verified local-currency quotes.

| Item | Monthly allocation | Approval condition |
| --- | --- | --- |
| OVH VPS, taxes and payment conversion included | At most GH₵140 | Confirm region, monthly billing, renewal price, storage and included traffic before ordering. |
| Oracle Always Free resources | GH₵0 | Verify account eligibility, home region, existing usage and selected resources before applying a plan. |
| Independent encrypted backup storage | At most GH₵25 | Quote storage, API requests, retrieval and transfer against measured data size. |
| Monitoring | GH₵0 incremental target | Use included host metrics and an external check within an explicitly verified free allowance. |
| Exchange-rate and growth reserve | GH₵35 | Do not consume it without revising the cost sheet. |
| Total allocation | GH₵200 | No purchase until the complete recurring quote fits. |

OVH’s US listing inspected during the audit advertises VPS-1 at $4.54 monthly with two vCores and 4 GB RAM, and VPS-2 at $8.50 with four vCores and 8 GB RAM. These are starting prices, not a Ghana checkout or renewal quote. Prefer 8 GB for operating margin if the final quote fits; 4 GB remains a benchmark-dependent option. [OVH VPS listing](https://us.ovhcloud.com/vps/)

Oracle’s current documentation gives Always Free A1 tenancies 1,500 OCPU-hours and 9,000 GB-hours monthly, equivalent to two OCPUs and 12 GB RAM. Combined boot and block storage is limited to 200 GB, with five volume backups in the home region. Idle instances can be reclaimed. Propose one A1 with two OCPUs, 12 GB RAM and a 50 GB boot volume only if the tenancy has the full remaining allowance. Do not assume older four-OCPU guidance applies. [Oracle Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)

Encode tenancy-wide remaining capacity in the infrastructure plan, including any existing instances and volumes. Refuse paid shapes, non-home-region storage and unapproved add-ons. Budget alerts are notifications, not a hard spending stop. Capacity shortages or reclamation are operational constraints, not reasons to provision a paid replacement automatically.

Keep model, search, SMTP, domain renewal and registry charges visible in a separate operating-cost section. If any of these must fit inside the same GH₵200 ceiling, reduce the server allocation before purchase. GitHub Actions and registry free allowances must be verified against repository visibility and account usage.

## Phase 1: Prepare reviewable configuration

Approval requested for this phase only at the end of the audit. It changes local version-controlled files and runs isolated tests. It does not change either server.

Planned deliverables in each `deploy` branch:

- Production Dockerfiles with pinned base-image versions or digests, complete lockfile installs, reviewed runtime identities and narrowly scoped build contexts. Reproduce the suspected editable-project installation issue before fixing it.
- A dedicated root `docker-compose.coolify.yml` using immutable image references and explicit variable injection. Keep existing development configuration available for development.
- Required-value guards for secrets, production mode and public origins. No production `.env` or key material enters Git or images. Public frontend values are the only build-time application settings.
- A one-shot migration service with `restart: "no"`, schema coordination and API and worker dependencies. Preserve Graduator’s migration lock and add equivalent protection for Blesser.
- Explicit persistent storage and a verified ownership strategy. Resolve Coolify-managed names before selecting stable external volumes. Preview deployments must never mount production volumes.
- Health checks for API, web entry points and workers, log rotation and initial resource bounds. Add database connection budgeting for API pools, worker pools, LISTEN connections, migrations and backup jobs.
- GitHub Actions release jobs for both architectures, including native ARM verification where available, tests before publication and immutable release metadata. Include the `deploy` branch in the intended workflow. Do not deploy every push to `main` accidentally.
- Backup, restore, migration, benchmark and health-check scripts with documented inputs, nonzero failure exits and no arbitrary `eval` hooks.
- `infra/` for provider configuration and host setup, `ops/` for scripts and systemd units, and `docs/` for procedures, cost evidence and action logs. Keep app-specific details in its own repository. Use one clear owner for any shared provider resources.

Implement host configuration with Ansible or idempotent shell plus cloud-init, and provider resources with OpenTofu where supported. Keep API credentials outside configuration. Encrypt and restrict state, which can contain secrets even when source files do not.

Use separate commits for container fixes, deployment configuration, operations and documentation. Stage owned files explicitly. Blesser’s existing UI edits and assets must remain outside deployment commits. Branches are currently local; publishing them or configuring remote workflows comes after the relevant implementation review.

## Phase 2: Prove the release in isolation

Use a working local Docker environment or dedicated CI test environment. Do not use existing development databases or volumes for destructive tests.

1. Build every deployable image from a fresh checkout on AMD64 and ARM64. Test the published manifest resolves correctly on each target. Run frontend checks and backend tests with the declared runtimes.
2. Start each complete stack with synthetic accounts, production-like settings and disposable credentials. Confirm schema migration from empty PostgreSQL and from the previous supported release. Missing secrets must fail clearly.
3. Verify database-backed `/ready`, public HTTPS behavior in a test proxy, member login, verification and reset mail through a test relay, admin authorization, SSR API reads and one queued research task with deterministic external-service fixtures.
4. Upload, preview and download supported document fixtures. For Blesser, verify a valid file above 2 MB succeeds up to the intended limit and an oversized request is rejected. For Graduator, verify PDF and DOCX exports, sandbox behavior and permissions.
5. Verify Graduator SSE events arrive promptly through both proxy layers. Test forwarded client address, secure origins, callback URLs and API outage behavior. Add equivalent tests for Blesser’s actual long-running endpoints.
6. Produce a consistent recovery set, retrieve it from the configured external destination and restore it into fresh isolated DB and file volumes. Compare expected Alembic heads, table counts, file hashes and encrypted-field readability. Log in and download a restored fixture.
7. Run both cross-architecture migration directions using the same release, PostgreSQL major version and synthetic dataset. Record transfer time, downtime and validation results.

An unavailable Docker daemon is an unresolved verification limit, not a passing gate. Current audit results are limited to five source configuration tests and shell syntax checks. None of the above integration gates has passed yet.

## Phase 3: Provision and secure approved servers

Present exact provider plans, costs, resource inventories and firewall diffs before applying them. Obtain explicit approval for paid resources and firewall changes.

- Record OS image, architecture, SSH public key fingerprint, disk allocation and provider console recovery path. Use a stable supported Ubuntu LTS image on both architectures.
- Create administrative access, verify a second SSH session, then apply key-only SSH and reviewed privileged access suitable for Coolify. Validate SSH configuration before reload. Schedule a timed firewall rollback until connectivity is verified.
- Apply provider network rules and Docker-aware host filtering for both IPv4 and IPv6. Public ingress is TCP 80 and 443. Restrict SSH to approved sources while retaining Coolify’s required local access. Database ports remain closed.
- Restrict temporary Coolify bootstrap access. Register the admin securely, configure its HTTPS hostname and verify dashboard, terminal and realtime connections. Public direct dashboard ports 8000, 6001 and 6002 can close once the domain works. [Coolify firewall guidance](https://coolify.io/docs/core/infrastructure/servers/firewall)
- Review and pin the Coolify installation version. Keep installer provenance, package versions and configuration in the action log. Configure security updates, clock synchronization, log limits and a maintenance procedure with reboot checks.
- Back up Coolify’s own database, installation secrets, proxy configuration and SSH material separately, encrypted outside both hosts. Confirm the documented recovery procedure for the installed release.

Rollback for this phase restores the previous SSH and firewall configuration using the open session or provider console. Remove only newly created, identified resources after a separate deletion approval. Do not delete volumes as an installation rollback.

## Phase 4: Connect Coolify and deploy privately

After approval, configure a separate least-privilege repository connection on each Coolify installation. Select `deploy`, the reviewed Compose file and the exact release. Protect deploy credentials and validate authenticated webhook handling. Deploy only after CI gates succeed.

Enter application secrets through Coolify’s protected environment configuration, separately per application. Store a recovery copy in an independent secrets store. Configure exact application, site and admin origins, OAuth callbacks, SMTP and spending limits. Never print environment dumps in evidence logs.

Keep public DNS unchanged while validating through temporary approved hostnames or controlled local resolution. Record the deployed Git revision, image manifest and architecture-specific digest, schema head, persistent-volume names, secret version identifiers and health results. Inspect the actual Coolify-rendered configuration without publishing expanded secret values.

Do not configure destructive automatic database migrations as an unreviewed side effect of a push. Snapshot and approve the release’s recovery point before schema changes. Only switch production DNS after the full test record is successful and a separate DNS approval is given.

## Phase 5: Operate backups, monitoring and benchmarks

Proposed disaster-recovery objectives are RPO 24 hours and RTO two hours, pending timed restore tests and business acceptance. Planned migration targets zero acknowledged-write loss and allows maintenance downtime. Daily dumps cannot guarantee zero data loss after an unexpected host failure.

For the first release, obtain a consistent backup by blocking writes, pausing scheduled work and draining or safely stopping API and worker writers. Dump PostgreSQL with the matching client and archive the shared file volume while writes remain stopped. Preserve the current application release and schema metadata. Resume only after the local set is complete. If this pause is unacceptable, design coordinated snapshots or WAL recovery before launch.

Use restrictive file permissions, checksums, a manifest and encrypted external storage independent of both VPS accounts. Transfer through authenticated TLS. Keep decryption keys outside the repository and backup bucket. Start with seven daily and four weekly recovery sets only if measured size fits the GH₵25 allocation. Retention pruning or deletion requires approval of the specific policy before enabling it. Never prune the last verified restore point because a new backup merely uploaded.

Run an isolated external-download restore weekly and after schema changes. Alert on failed or stale backups and restore failures. Cover uploads, database and the secrets needed for decryption, as well as independent Coolify recovery. A provider snapshot or a copy on the other application host is supplemental, not the only external backup.

Monitor HTTPS from outside the host, certificate expiry, DB readiness, per-worker heartbeat, queue age, errors, CPU, RAM, swap, disk space, inodes, restart count and backup age. Initial review thresholds are disk above 75 percent, memory above 80 percent sustained, backup older than 26 hours and a worker heartbeat older than its code-defined stale interval. Tune after baselining. Keep alerts and monitoring credentials independent of the host being checked.

Benchmark only approved targets. Record CPU model, architecture, RAM, OS, storage, release digests and worker settings. Run bounded CPU and memory tests, a small `fio` scratch-file workload outside data paths, `pgbench` against a disposable database, HTTP load and a representative queued-task workload. Separate external model latency and cost from server performance. Never run a raw-device write benchmark.

Publish p50 and p95 latency, throughput, errors, CPU and RSS, queue completion time, backup and restore duration, data size and disk growth. Reserve enough resources to restore or temporarily host the second application. Cross-provider migration of either app is not proven unless the destination can sustain the incoming app alongside its existing workload, or an approved relocation sequence creates room.

Record actual monthly invoices, tax, payment exchange rate, backup bytes and API requests, registry and CI use, bandwidth and forecast growth. Alert before the GH₵200 ceiling. Provider list prices are planning inputs until replaced with the actual account quote.

## Phase 6: Rehearse migration and approve cutover

1. Prepare the destination with the same application release and PostgreSQL 16, separate volumes and original secret material. Verify free capacity without touching the other app’s data.
2. Test restoration on the alternate architecture using synthetic data first. Record schema, row and file comparisons, decrypted field reads, login, queued work, uploads and HTTPS behavior in both directions.
3. Before a real move, request approval for the maintenance window and DNS changes. Reduce DNS TTL in advance only with approval. Pause webhooks, timers and scheduled sends as necessary.
4. Fence the source against new writes at every route and background writer. Drain active work, terminate live sessions or connections safely and prevent automatic restarts from creating a second writer. Record the final recovery boundary.
5. Create and verify the final DB and file recovery set. Transfer it encrypted, restore to fresh destination volumes, verify keys, schema and hashes, and test through controlled resolution while destination remains closed to users.
6. Obtain the approved DNS cutover, then open destination writes. Keep the source fenced during DNS propagation so clients with cached records cannot write to it. Observe health, errors and task recovery before declaring migration successful.
7. Retain the original source data for the agreed period. Data deletion or resource removal requires separate approval.

Rollback before destination writes can return traffic to the unchanged source. After destination accepts writes, do not point DNS back to the stale source. Fence the destination, create another consistent recovery set, restore it back to the source and validate before switching. This reverse transfer requires the same downtime and approval discipline. Reconcile external side effects such as email and billing to avoid replaying them.

For a schema-incompatible release, restore the matching DB and files into fresh volumes with the previous image. Changing an image tag alone is not a database rollback. All restore tooling must require an explicit target, refuse the active production target by default and retain the original data.

## Approval and completion criteria

The next approval is limited to Phase 1 configuration implementation and Phase 2 isolated tests. Server provisioning, Coolify installation, paid services, firewall rules, production DNS and data deletion remain separately gated by the user’s instructions.

Both deployments remain incomplete until successful builds on both architectures, running health and functional checks, externally retrieved backup restoration and bidirectional migration rehearsals have recorded evidence. Provisioning scripts need idempotence checks, security changes need connectivity verification, and benchmarks and actual costs must be documented.

Before infrastructure work, resolve the OVH specification and renewal quote, Oracle home region and remaining tenancy capacity, application domains, SSH access method, existing production data size, acceptable maintenance window, external backup destination and the scope of the GH₵200 ceiling. Never request credentials in chat or commit them to resolve these questions.
