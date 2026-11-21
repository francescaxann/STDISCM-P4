# Distributed Online Enrollment System

This workspace implements a runnable seven-container enrollment cluster using Flask MVC, Python gRPC, PostgreSQL streaming replication, JWTs, row-locking, and fault-isolation patterns.

## Topology

| Node | Host | Port |
|---|---|---|
| View/API gateway | `view-node` | 8080 |
| Auth | `auth-node` | 50051 |
| Courses/enrollment | `course-node` | 50052 |
| Grades | `grade-node` | 50053 |
| Audit | `audit-node` | 50054 |
| PostgreSQL primary | `db-primary` | 5432 |
| PostgreSQL replica | `db-replica` | 5432 |

## Docker quick start

Docker Desktop or Docker Engine is required.

```bash
cd "/Users/francescacatolico/Downloads/STDISCM P4"
docker compose build
docker compose up -d
```

Open `https://localhost:8443`. Accept the browser warning for the generated self-signed certificate.

Run the repeatable end-to-end smoke test:

```bash
./smoke_test.sh
```

Seed credentials:

- Student: `student` / `1234`
- Faculty: `faculty` / `1234`

The student UUID is `11111111-1111-1111-1111-111111111111`. The faculty UUID is `22222222-2222-2222-2222-222222222222`.

Check containers:

```bash
docker compose ps
docker compose logs -f view-node course-node grade-node
```

Rebuild generated gRPC code manually:

```bash
python3 -m pip install grpcio grpcio-tools psycopg2-binary flask pyjwt
./compile_proto.sh
```

## Docker replication setup

The primary initializes the `enrollment` database and schema through `/docker-entrypoint-initdb.d`. The replica first waits for the primary and then uses `pg_basebackup -R` to become a hot standby. Primary writes are made in `auth-node`, `course-node`, `grade-node`, and `audit-node`. Course and grade reads try `db-replica` first and fall back to `db-primary`.

Verify replication:

```bash
docker compose exec db-primary psql -U postgres -d enrollment -c 'SELECT application_name,state,sync_state FROM pg_stat_replication;'
docker compose exec db-replica psql -U postgres -d enrollment -c 'SELECT pg_is_in_recovery();'
```

## Bare-metal / separate-machine setup

1. Install Python 3.12+, PostgreSQL 16, pip dependencies, and OpenSSL-capable hosts.
2. Initialize and start PostgreSQL on primary host `DB_PRIMARY_IP`:

```bash
createdb enrollment
psql -d enrollment -f db/init.sql
psql -d enrollment -f db/replication.sql
```

Configure `postgresql.conf` with `wal_level=replica`, `max_wal_senders=10`, `max_replication_slots=10`, and `hot_standby=on`. Add this to `pg_hba.conf`:

```text
host replication replicator 0.0.0.0/0 md5
host all all 0.0.0.0/0 md5
```

Restart PostgreSQL and create the standby from the primary:

```bash
pg_basebackup -h DB_PRIMARY_IP -D /var/lib/postgresql/16/standby -U replicator -v -P -R
sudo -u postgres postgres -D /var/lib/postgresql/16/standby
```

On all machines:

```bash
python3 -m pip install -r requirements.txt
./compile_proto.sh
```

Create `requirements.txt` in your environment if not already generated, containing:

```text
flask
grpcio
grpcio-tools
psycopg2-binary
pyjwt
```

Run processes on their hosts:

```bash
DB_PRIMARY=DB_PRIMARY_IP JWT_SECRET=dev-enrollment-secret python3 auth-node/server.py
DB_PRIMARY=DB_PRIMARY_IP DB_REPLICA=DB_REPLICA_IP AUDIT_HOST=AUDIT_IP python3 course-node/server.py
DB_PRIMARY=DB_PRIMARY_IP DB_REPLICA=DB_REPLICA_IP AUDIT_HOST=AUDIT_IP python3 grade-node/server.py
DB_PRIMARY=DB_PRIMARY_IP python3 audit-node/server.py
AUTH_HOST=AUTH_IP COURSE_HOST=COURSE_IP GRADE_HOST=GRADE_IP JWT_SECRET=dev-enrollment-secret python3 view-node/app.py
```

Open TCP firewall rules for ports 8080, 50051-50054, 5432, and 5433 where applicable.

## Fault-tolerance tests

Every test should begin with `docker compose up -d` and login with a student session.

### Stop auth-node

```bash
docker compose stop auth-node
```

- Existing browser session remains usable because the view verifies the local JWT signature.
- Logout or a new login shows an unavailable authentication warning.
- Courses and grades continue to work.

Restart: `docker compose start auth-node`.

### Stop course-node

```bash
docker compose stop course-node
```

- `/courses` displays `Unavailable` and enrollment fails safely.
- Login, dashboard, logout, and grades remain working.

Restart: `docker compose start course-node`.

### Stop grade-node

```bash
docker compose stop grade-node
```

- `/grades` displays `Unavailable`.
- Login, courses, and enrollment remain working.

Restart: `docker compose start grade-node`.

### Stop audit-node

```bash
docker compose stop audit-node
```

- Enrollment and grade upload still succeed; audit RPC calls time out at 0.5 seconds and are discarded.
- No audit UI state is affected.

Restart: `docker compose start audit-node`.

### Stop db-replica

```bash
docker compose stop db-replica
```

- Open-courses and student-grade reads automatically fall back to `db-primary`.
- Enroll and faculty uploads continue because writes target the primary.

Restart: `docker compose start db-replica`.

### Stop db-primary

```bash
docker compose stop db-primary
```

- Login/logout, enrollment, grade writes, and audit writes backed by the primary become unavailable.
- The UI remains reachable and unrelated in-browser pages render with unavailable warnings where appropriate.

## Concurrency and consistency

Enrollment uses `BEGIN`, `SELECT ... FOR UPDATE`, slot validation, an insert, and a slot decrement in one transaction. The row lock serializes concurrent enrollment attempts for a course. The primary is the only write endpoint. Reads prefer the replica and catch connection failures to fall back to the primary. gRPC calls from the view use a strict 2-second deadline and one retry for read calls on `UNAVAILABLE` or `DEADLINE_EXCEEDED`.
