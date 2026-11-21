#!/bin/bash
set -e
mkdir -p /var/lib/postgresql/data/pgdata
if [[ $(cat /var/lib/postgresql/data/pgdata/PG_VERSION 2>/dev/null) == "" ]]; then
  initdb -D /var/lib/postgresql/data/pgdata
fi
cat >> /var/lib/postgresql/data/pgdata/postgresql.conf <<'EOF'
listen_addresses='*'
wal_level=replica
max_wal_senders=10
max_replication_slots=10
hot_standby=on
EOF
cat >> /var/lib/postgresql/data/pgdata/pg_hba.conf <<'EOF'
host replication replicator 0.0.0.0/0 md5
EOF
postgres -D /var/lib/postgresql/data/pgdata
