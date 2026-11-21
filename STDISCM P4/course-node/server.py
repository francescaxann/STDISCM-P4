import os, sys
from concurrent import futures
import grpc
import enrollment_pb2, enrollment_pb2_grpc
sys.path.append('/app')
from common.db import pool, connection, optional_pool

primary=pool(os.getenv('DB_PRIMARY','db-primary'))
replica_host=os.getenv('DB_REPLICA','db-replica')
replica=optional_pool(replica_host)

class Course(enrollment_pb2_grpc.CourseServiceServicer):
    def GetOpenCourses(self, req, context):
        db=replica
        try:
            with connection(db) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id,code,title,slots_available FROM courses WHERE slots_available>0 ORDER BY id")
                    rows=cur.fetchall()
        except Exception:
            with connection(primary) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id,code,title,slots_available FROM courses WHERE slots_available>0 ORDER BY id")
                    rows=cur.fetchall()
        return enrollment_pb2.CoursesResponse(courses=[enrollment_pb2.Course(id=r[0],code=r[1],title=r[2],slots_available=r[3]) for r in rows])
    def EnrollStudent(self, req, context):
        if req.role!='STUDENT': return enrollment_pb2.EnrollResponse(success=False,message='Only students may enroll')
        try:
            with connection(primary) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT slots_available FROM courses WHERE id=%s FOR UPDATE",(req.course_id,))
                    row=cur.fetchone()
                    if not row: return enrollment_pb2.EnrollResponse(success=False,message='Course not found')
                    if row[0]<=0:
                        conn.rollback(); return enrollment_pb2.EnrollResponse(success=False,message='Course is full')
                    cur.execute("INSERT INTO enrollments(student_id,course_id) VALUES(%s,%s) ON CONFLICT DO NOTHING RETURNING id",(req.user_id,req.course_id))
                    if not cur.fetchone():
                        conn.rollback(); return enrollment_pb2.EnrollResponse(success=False,message='Already enrolled')
                    cur.execute("UPDATE courses SET slots_available=slots_available-1 WHERE id=%s",(req.course_id,))
                conn.commit()
            # best-effort audit
            try:
                import grpc
                audit=grpc.channel_ready_future(grpc.insecure_channel(os.getenv('AUDIT_HOST','audit-node')+':50054',options=[('grpc.lb_policy_name','pick_first')]))
                audit.result(timeout=.5)
                import enrollment_pb2 as pb, enrollment_pb2_grpc as pbg
                stub=pbg.AuditServiceStub(grpc.insecure_channel(os.getenv('AUDIT_HOST','audit-node')+':50054'))
                stub.LogEvent(pb.AuditEvent(event_type='ENROLLMENT',actor_id=req.user_id,details=f'course_id={req.course_id}'),timeout=.5)
            except Exception: pass
            return enrollment_pb2.EnrollResponse(success=True,message='Enrolled successfully')
        except Exception as e:
            context.abort(grpc.StatusCode.UNAVAILABLE,'Primary database unavailable')

server=grpc.server(futures.ThreadPoolExecutor(max_workers=20)); enrollment_pb2_grpc.add_CourseServiceServicer_to_server(Course(),server); server.add_insecure_port('[::]:50052'); server.start(); server.wait_for_termination()
