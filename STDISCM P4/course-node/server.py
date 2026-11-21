import os, sys
from concurrent import futures
import grpc
import enrollment_pb2, enrollment_pb2_grpc
sys.path.append('/app')
from common.db import pool, connection, LazyReplicaPool
from common.audit import audit_event
from common.grpc_auth import verified_identity

primary=pool(os.getenv('DB_PRIMARY','db-primary'))
replica_host=os.getenv('DB_REPLICA','db-replica')
replica=LazyReplicaPool(replica_host)

class Course(enrollment_pb2_grpc.CourseServiceServicer):
    def GetOpenCourses(self, req, context):
        replica_pool = replica.get()
        if replica_pool is not None:
            try:
                with connection(replica_pool) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT id,code,title,slots_available FROM courses WHERE slots_available>0 ORDER BY id")
                        rows = cur.fetchall()
            except Exception:
                replica.pool = None
                rows = None
        else:
            rows = None
        if rows is None:
            try:
                with connection(primary) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT id,code,title,slots_available FROM courses WHERE slots_available>0 ORDER BY id")
                        rows = cur.fetchall()
            except Exception:
                context.abort(grpc.StatusCode.UNAVAILABLE, "Primary database unavailable")
        return enrollment_pb2.CoursesResponse(courses=[enrollment_pb2.Course(id=r[0],code=r[1],title=r[2],slots_available=r[3]) for r in rows])

    def EnrollStudent(self, req, context):
        identity = verified_identity(context)
        if not identity:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing or invalid JWT")
        if identity["role"] != "STUDENT":
            return enrollment_pb2.EnrollResponse(success=False, message="Only students may enroll")
        try:
            with connection(primary) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id FROM courses WHERE id=%s FOR UPDATE", (req.course_id,))
                    course = cur.fetchone()
                    if not course:
                        conn.rollback()
                        return enrollment_pb2.EnrollResponse(success=False, message="Course not found")
                    cur.execute("SELECT id FROM enrollments WHERE student_id=%s AND course_id=%s", (identity["user_id"], req.course_id))
                    if cur.fetchone():
                        conn.rollback()
                        return enrollment_pb2.EnrollResponse(success=False, message="Already enrolled")
                    cur.execute("SELECT slots_available FROM courses WHERE id=%s FOR UPDATE", (req.course_id,))
                    row = cur.fetchone()
                    if not row or row[0] <= 0:
                        conn.rollback()
                        return enrollment_pb2.EnrollResponse(success=False, message="Course is full")
                    cur.execute("INSERT INTO enrollments(student_id,course_id) VALUES(%s,%s)", (identity["user_id"], req.course_id))
                    cur.execute("UPDATE courses SET slots_available=slots_available-1 WHERE id=%s", (req.course_id,))
                conn.commit()
            audit_event("ENROLLMENT", identity["user_id"], f"course_id={req.course_id}")
            try:
                md = dict(context.invocation_metadata())
                token = md.get("authorization", "")
                audit_channel = grpc.insecure_channel(
                    os.getenv("AUDIT_HOST", "audit-node") + ":50054",
                    options=(("grpc.max_reconnect_backoff_ms", 1000),))
                audit_stub = enrollment_pb2_grpc.AuditServiceStub(audit_channel)
                audit_stub.CreateReceipt(
                    enrollment_pb2.Receipt(
                        student_id=identity["user_id"], course_id=req.course_id,
                        status="ENROLLED", details=f"Enrollment receipt for course {req.course_id}"),
                    timeout=0.5, metadata=(("authorization", token),))
            except Exception:
                pass
            return enrollment_pb2.EnrollResponse(success=True, message="Enrolled successfully")
        except Exception:
            context.abort(grpc.StatusCode.UNAVAILABLE, "Primary database unavailable")

server=grpc.server(futures.ThreadPoolExecutor(max_workers=20))
enrollment_pb2_grpc.add_CourseServiceServicer_to_server(Course(),server)
server.add_insecure_port('[::]:50052')
server.start(); server.wait_for_termination()
