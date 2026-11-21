import os
import time
from contextlib import contextmanager
from psycopg2.pool import ThreadedConnectionPool


def pool(host, db='enrollment', user='postgres', password='postgres', minconn=2, maxconn=10, retries=30):
    last_error = None
    for attempt in range(retries):
        try:
            return ThreadedConnectionPool(minconn, maxconn,
                host=host, port=5432, dbname=db, user=user, password=password,
                connect_timeout=2)
        except Exception as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(2)
    raise last_error or RuntimeError("Could not initialize database connection pool")


def optional_pool(host, db='enrollment', user='postgres', password='postgres', minconn=2, maxconn=10):
    try:
        return ThreadedConnectionPool(minconn, maxconn,
            host=host, port=5432, dbname=db, user=user, password=password,
            connect_timeout=2)
    except Exception:
        return None


@contextmanager
def connection(pool_obj):
    conn = pool_obj.getconn()
    try:
        yield conn
    except Exception:
        if not conn.closed:
            conn.rollback()
        raise
    finally:
        pool_obj.putconn(conn)


def read_pool(primary_pool, replica_host):
    import psycopg2
    try:
        return ThreadedConnectionPool(2, 10, host=replica_host, port=5432,
            dbname='enrollment', user='postgres', password='postgres', connect_timeout=2)
    except Exception:
        return primary_pool
