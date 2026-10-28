# Load tests

The API was load-tested on AWS to check the claim in
[Scaling](overview.md#scaling): any replica can serve any request, so capacity
grows with the replica count. **All four scenarios scaled linearly from one to
eight replicas.** The bottleneck was always the replicas' CPU, never a shared
resource.

The capacity of a single replica only holds for this setup, small Fargate
tasks on an AWS Free plan account. Treat it as a measurement, not a
specification. On a bigger task the absolute numbers change. The linear shape
should not.

## Results

Each scenario ran against 1, 2, 4 and 8 replicas, at load steps that grow with
the replica count. "Sustained" is the highest step that met the criterion in
[Sustained](#sustained). If capacity is linear, every replica count breaks at
the same step per replica.

| Scenario | What a request does | Sustained per replica | 1 → 2 → 4 → 8 replicas, sustained req/s |
|---|---|---|---|
| `GET /health` | HTTP only: no database, no hashing | ~1,000 (CPU saturates at ~950–1,050) | 500 → 2,000 → not run → not run |
| `POST /auth/login` | argon2 verify, one read, one refresh-token write | 8 (saturates at ~10) | 8 → 16 → 32 → 64 |
| Signed-in session | 80 % `GET /auth/me` (JWT + one read), 20 % `POST /auth/refresh` (rotation, two writes) | 80 (saturates at ~100) | 80 → 160 → 320 → 640 |
| `POST /auth/register` | argon2 hash, two inserts, an email dispatch, 500 ms response floor | 6 (saturates at ~8) | 6 → 12 → 24 → 48 |

- **`/health` stopped at two replicas.** Two replicas needed ~2,000 req/s, which
  already pushed the load generator's CPU to a p90 of 85 %. Four or eight would
  have measured the generator, not the API. One replica's step at 1,000 req/s
  failed only because 1.3 % of requests were dropped. CloudWatch shows the
  replica saturating at ~950 req/s, and two replicas at ~2,100.
- **Password hashing dominates login and register.** argon2 at the OWASP minimum
  profile costs ~32 ms of CPU per hash on a 0.5 vCPU task, about twice what it
  costs on a laptop core. An estimate made locally overstates a replica's
  capacity by a factor of two to three.
- **A replica's capacity varies with the host it lands on.** In one register
  run, the single-replica task sustained 10 req/s instead of 6, while using ~30 %
  less CPU per request than every other run. Fargate does not promise the same
  CPU generation on every host.

## Shared resources

None of these was the limit at eight replicas. All of them were closer than the
replicas' CPU suggests.

| Resource | Peak across the runs | What it means |
|---|---|---|
| Postgres CPU (`db.t4g.micro`) | 41 % (session, ~800 req/s) | The next limit, though still far. A burstable instance also drops to its baseline once its CPU credits run out. |
| Postgres connections | 68 of 79 (register, 8 replicas) | A ninth replica needs a pooler or a larger instance. See [Scaling](overview.md#scaling). |
| Redis memory (`cache.t4g.micro`) | ~13 %, with ~29,000 queued email dispatches | Fine once each queued email is held only once. |
| Email worker (1 task, `--concurrency 4`) | ~2.7 emails/s | Did not keep up: see below. |

**The email worker does not scale with the API on its own.** Register at eight
replicas accepted ~35,000 signups in about half an hour. One worker sends each
email in about a second, four at a time, so it left ~29,000 verification emails
`PENDING`. None was lost, but draining them takes hours. Scale workers together
with API replicas.

**Saturation shows up as `500` errors, not only as latency.** Past its limit, a
replica's requests wait for CPU while holding a pooled database connection. The
pool (`DB_POOL_SIZE` 4 + `DB_MAX_OVERFLOW` 4 in these runs) runs out, and
requests that wait longer than `DB_POOL_TIMEOUT` (3 s) fail with
`QueuePool limit … reached`. CPU-based autoscaling, with headroom below 100 %,
keeps replicas out of that zone.

**The outbox sweep used to amplify a backlog.** In the first register run, the
sweep re-queued every stale `PENDING` row each minute, including rows still
waiting in the broker. Redis memory kept climbing after the load stopped. The
sweep now skips while dispatches are still queued. A rerun of the same test
showed Redis memory flat as soon as the load ended. See
[ADR 3](decisions/0003-durable-email-outbox-before-dispatch.md).

## How the tests were run

The infrastructure code and the test scripts are not part of this repository.
This section describes them in enough detail to rebuild them.

### On an AWS Free plan account

Every run used an AWS account on the
[Free plan](https://aws.amazon.com/free/), the credit-based plan for new
accounts. Its credits covered every charge, and nothing was billed. The plan
only allows small instance types, which is why the database and Redis are
`micro` instances.

Fargate tasks, the load balancer and public IPv4 addresses are not free: they
draw down the plan's credits by the hour, whether or not a test is running.
If you replicate this:

- Set a budget alert before you start.
- Scale every ECS service to zero, or tear the stack down, between test sessions.
- Run the tasks in public subnets with public IPs, as these tests did, rather
  than in private subnets behind a NAT gateway, which adds an hourly charge of
  its own. The tasks' security group only admits traffic from the load balancer
  and from the other tasks.

### Infrastructure

Region `eu-west-1`, built with Terraform.

| Piece | Configuration |
|---|---|
| API | ECS Fargate, 0.5 vCPU and 1 GiB per task, one uvicorn process, pool 4 + 4 connections |
| Worker | One Fargate task, `celery worker --concurrency 4` |
| Beat | One Fargate task |
| Email | Mailpit as the SMTP server, as a Fargate service in the cluster |
| Postgres | RDS Postgres 17, `db.t4g.micro`, single-AZ, 20 GiB, 79 connections |
| Redis | ElastiCache Redis 7.1, `cache.t4g.micro` |
| Load balancer | Application Load Balancer across two availability zones, HTTP on port 80 |
| App settings | `RATE_LIMIT_ENABLED=false` and the Have I Been Pwned check off, so neither is what gets measured |

Autoscaling targets 60 % average CPU between 2 and 8 replicas. Each run pinned
the minimum and the maximum to the replica count under test.

### Load generator

[k6](https://k6.io/) 2.3 on an 8-core local VM, about 48 ms away from the
region. Every latency k6 reports includes that round trip.

- **Open model.** One `ramping-arrival-rate` scenario holds each rate for 60 s,
  with a 10 s ramp between steps. Arrivals keep coming whether or not the API
  keeps up, so saturation shows as latency and errors rather than as a slower
  client.
- **Steps scale with replicas.** Each run multiplies a per-replica staircase by
  the replica count: login used 2, 4, 6, 8, 10 and 12 req/s per replica, so
  eight replicas ran 16 up to 96 req/s.
- **Watch the generator.** Record its CPU during each run. If it saturates, the
  results describe the generator, not the API. Past ~2,000 req/s, run k6 inside
  the region, as ECS tasks or on an EC2 instance.

The scenarios:

- **`/health`**: plain `GET`s.
- **Login**: 1,000 verified users seeded in the database. Each request signs in
  a random one.
- **Session**: k6's `setup()` signs in 300 seeded users before the first step,
  so argon2 stays out of the measurement. Each virtual user keeps its own
  session, because refresh tokens are single use. 80 % of iterations call
  `/auth/me` and 20 % rotate the refresh token.
- **Register**: every request registers a new, unique address.

### Sustained

A step is sustained when its p95 latency stays under 500 ms and under 1 % of
its requests fail or are dropped (k6 drops a request it has no free virtual
user to start on time). Register gets 1,000 ms instead, because it holds every
response to its 500 ms floor.

### The server-side view

k6 only shows what the generator saw. These CloudWatch metrics, minute by minute
over each run's window, show whether the API or the generator gave out:

| Metric | Statistic | What it shows |
|---|---|---|
| `AWS/ECS` `CPUUtilization`, per service | Maximum | The busiest replica |
| `AWS/ApplicationELB` `RequestCount` | Sum ÷ 60 | Requests per second that reached AWS |
| `AWS/ApplicationELB` `TargetResponseTime` | p95 | A replica's response time, without the network |
| `AWS/ApplicationELB` `HTTPCode_Target_5XX_Count`, `HTTPCode_ELB_5XX_Count` | Sum | Errors from the app versus from the load balancer |
| `AWS/RDS` `CPUUtilization`, `DatabaseConnections` | Maximum | Whether Postgres is the limit |
| `AWS/ElastiCache` `DatabaseMemoryUsagePercentage` | Maximum | Whether the task queue is growing |

For register, also query the `email_outbox` table for each run's time window.
Count rows by `status`, and compute `sent_at - created_at` for the sent ones.
That shows whether the worker kept up. The database is in a private subnet, so
run the query as a one-off ECS task with the backend image.

The results come from images `3490ae17` and `33c3a36c` (the rerun of register,
after the sweep fix), on 2026-10-27.
