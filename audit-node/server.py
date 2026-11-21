import os, sys
from concurrent import futures
import grpc
import enrollment_pb2, enrollment_pb2_grpc
sys.path.append('/app')
from common.db import pool, connection
pool_obj=pool(os.getenv('DB_PRIMARY','db-primary'))
class Audit(enrollment_pb2_grpc.AuditServiceServicer):
    def LogEvent(self,req,context):
        try:
            with connection(pool_obj) as conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO audit_log(event_type,actor_id,details) VALUES(%s,%s,%s)",(req.event_type,req.actor_id,req.details))
                conn.commit()
            return enrollment_pb2.AuditResponse(accepted=True)
        except Exception:
            context.abort(grpc.StatusCode.UNAVAILABLE,'Audit database unavailable')
server=grpc.server(futures.ThreadPoolExecutor(max_workers=10)); enrollment_pb2_grpc.add_AuditServiceServicer_to_server(Audit(),server); server.add_insecure_port('[::]:50054'); server.start(); server.wait_for_termination()
