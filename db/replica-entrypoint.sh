#!/bin/bash
set -e
until PGPASSWORD=postgres pg_isready -h db-primary -p 5432 -U postgres; do sleep 2; done
if [[ ! -f /var/lib/postgresql/data/PG_VERSION ]]; then
 rm -rf /var/lib/postgresql/data/*
 PGPASSWORD=replica_password pg_basebackup -h db-primary -D /var/lib/postgresql/data -U replicator -v -P -R
fi
chown -R postgres:postgres /var/lib/postgresql/data
exec gosu postgres postgres -c hot_standby=on
