import os
import time
from contextlib import contextmanager
from psycopg2.pool import ThreadedConnectionPool
from psycopg2 import OperationalError


def pool(host, db="enrollment", user="postgres", password="postgres", minconn=2, maxconn=10, retries=30):
    last_error = None
    for attempt in range(retries):
        try:
            kwargs = dict(dbname=db, user=user, password=password, connect_timeout=2)
            if host in (os.getenv("DB_PRIMARY", "db-primary"), "db-primary"):
                replica = os.getenv("DB_REPLICA", "db-replica")
                kwargs["dsn"] = primary_read_dsn(host, replica)
            else:
                kwargs.update(host=host, port=5432)
            return ThreadedConnectionPool(minconn, maxconn, **kwargs)
        except Exception as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(2)
    raise last_error or RuntimeError("Could not initialize database pool")


class LazyReplicaPool:
    def __init__(self, host, cooldown=5.0, **kwargs):
        self.host = host
        self.cooldown = cooldown
        self.kwargs = kwargs
        self.pool = None
        self.next_attempt = 0

    def get(self):
        now = time.monotonic()
        if self.pool is not None:
            return self.pool
        if now < self.next_attempt:
            return None
        self.next_attempt = now + self.cooldown
        try:
            self.pool = pool(self.host, retries=1, **self.kwargs)
        except Exception:
            self.pool = None
        return self.pool


@contextmanager
def connection(pool_obj):
    conn = pool_obj.getconn()
    try:
        yield conn
    except OperationalError:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            pool_obj.putconn(conn, close=True)
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
        raise
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            if not getattr(conn, "closed", False):
                pool_obj.putconn(conn)
        except Exception:
            try:
                conn.close()
            except Exception:
                pass


def primary_read_dsn(primary_host="db-primary", replica_host="db-replica"):
    return (
        f"host='{primary_host},{replica_host}' port=5432 dbname=enrollment "
        "user=postgres password=postgres target_session_attrs=read-write connect_timeout=2"
    )
