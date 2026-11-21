import os, sys
from concurrent import futures
import grpc
import enrollment_pb2, enrollment_pb2_grpc
sys.path.append('/app')
from common.db import pool, connection, optional_pool
primary=pool(os.getenv('DB_PRIMARY','db-primary'))
replica=optional_pool(os.getenv('DB_REPLICA','db-replica'))

def audit(event,actor,details):
    try:
        chan=grpc.insecure_channel(os.getenv('AUDIT_HOST','audit-node')+':50054')
        enrollment_pb2_grpc.AuditServiceStub(chan).LogEvent(enrollment_pb2.AuditEvent(event_type=event,actor_id=actor,details=details),timeout=.5)
    except Exception: pass

class Grades(enrollment_pb2_grpc.GradeServiceServicer):
    def GetStudentGrades(self, req, context):
        if req.role!='STUDENT': return enrollment_pb2.GradesResponse()
        try:
            with connection(replica) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT g.course_id,c.code,c.title,g.grade FROM grades g JOIN courses c ON c.id=g.course_id WHERE g.student_id=%s",(req.user_id,)); rows=cur.fetchall()
        except Exception:
            try:
                with connection(primary) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT g.course_id,c.code,c.title,g.grade FROM grades g JOIN courses c ON c.id=g.course_id WHERE g.student_id=%s",(req.user_id,)); rows=cur.fetchall()
            except Exception:
                context.abort(grpc.StatusCode.UNAVAILABLE,'Database unavailable')
        return enrollment_pb2.GradesResponse(grades=[enrollment_pb2.Grade(course_id=r[0],course_code=r[1],course_title=r[2],grade=r[3]) for r in rows])
    def UploadGrade(self, req, context):
        if req.role!='FACULTY': return enrollment_pb2.UploadGradeResponse(success=False,message='Only faculty may upload grades')
        try:
            with connection(primary) as conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO grades(student_id,course_id,grade) VALUES(%s,%s,%s) ON CONFLICT(student_id,course_id) DO UPDATE SET grade=EXCLUDED.grade",(req.student_id,req.course_id,req.grade))
                conn.commit()
            audit('GRADE_UPLOAD',req.user_id,f'student={req.student_id},course_id={req.course_id},grade={req.grade}')
            return enrollment_pb2.UploadGradeResponse(success=True,message='Grade saved')
        except Exception:
            context.abort(grpc.StatusCode.UNAVAILABLE,'Primary database unavailable')

server=grpc.server(futures.ThreadPoolExecutor(max_workers=20)); enrollment_pb2_grpc.add_GradeServiceServicer_to_server(Grades(),server); server.add_insecure_port('[::]:50053'); server.start(); server.wait_for_termination()
