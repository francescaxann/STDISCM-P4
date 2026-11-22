import os, sys
from concurrent import futures
import grpc
import enrollment_pb2, enrollment_pb2_grpc
sys.path.append('/app')
from common.db import pool, connection, LazyReplicaPool
from common.audit import audit_event
from common.grpc_auth import verified_identity
primary=pool(os.getenv('DB_PRIMARY','db-primary'))
replica=LazyReplicaPool(os.getenv('DB_REPLICA','db-replica'))

from psycopg2 import OperationalError, IntegrityError, DataError

class Grades(enrollment_pb2_grpc.GradeServiceServicer):
    def GetStudentGrades(self, req, context):
        identity=verified_identity(context)
        if not identity:
            context.abort(grpc.StatusCode.UNAUTHENTICATED,"Missing or invalid JWT")
        if identity["role"]=="STUDENT":
            student_id=identity["user_id"]
        elif identity["role"]=="FACULTY":
            student_id=None
        else:
            return enrollment_pb2.GradesResponse()
        replica_pool=replica.get()
        try:
            db=replica_pool or primary
            with connection(db) as conn:
                with conn.cursor() as cur:
                    if student_id:
                        cur.execute("SELECT g.course_id,c.code,c.title,g.grade,u.username,g.student_id FROM grades g JOIN courses c ON c.id=g.course_id JOIN users u ON u.id=g.student_id WHERE g.student_id=%s",(student_id,))
                    else:
                        cur.execute("SELECT g.course_id,c.code,c.title,g.grade,u.username,g.student_id FROM grades g JOIN courses c ON c.id=g.course_id JOIN users u ON u.id=g.student_id")
                    rows=cur.fetchall()
        except OperationalError:
            try:
                with connection(primary) as conn:
                    with conn.cursor() as cur:
                        if student_id:
                            cur.execute("SELECT g.course_id,c.code,c.title,g.grade,u.username,g.student_id FROM grades g JOIN courses c ON c.id=g.course_id JOIN users u ON u.id=g.student_id WHERE g.student_id=%s",(student_id,))
                        else:
                            cur.execute("SELECT g.course_id,c.code,c.title,g.grade,u.username,g.student_id FROM grades g JOIN courses c ON c.id=g.course_id JOIN users u ON u.id=g.student_id")
                        rows=cur.fetchall()
            except Exception:
                context.abort(grpc.StatusCode.UNAVAILABLE,"Database unavailable")
        except Exception:
            context.abort(grpc.StatusCode.INTERNAL,"Could not retrieve grades")
        return enrollment_pb2.GradesResponse(grades=[enrollment_pb2.Grade(course_id=r[0],course_code=r[1],course_title=r[2],grade=r[3],student_name=r[4] or "",student_id=r[5] or "") for r in rows])

    def UploadGrade(self, req, context):
        identity=verified_identity(context)
        if not identity:
            context.abort(grpc.StatusCode.UNAUTHENTICATED,"Missing or invalid JWT")
        if identity["role"]!="FACULTY":
            return enrollment_pb2.UploadGradeResponse(success=False,message="Only faculty may upload grades")
        try:
            with connection(primary) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM enrollments WHERE student_id=%s AND course_id=%s",(req.student_id,req.course_id))
                    if not cur.fetchone():
                        conn.rollback()
                        return enrollment_pb2.UploadGradeResponse(success=False,message="Student is not enrolled in this course")
                    cur.execute("INSERT INTO grades(student_id,course_id,grade) VALUES(%s,%s,%s) ON CONFLICT(student_id,course_id) DO UPDATE SET grade=EXCLUDED.grade",(req.student_id,req.course_id,req.grade))
                conn.commit()
            audit_event("GRADE_UPLOAD",identity["user_id"],f"student={req.student_id},course_id={req.course_id},grade={req.grade}")
            return enrollment_pb2.UploadGradeResponse(success=True,message="Grade saved")
        except IntegrityError:
            return enrollment_pb2.UploadGradeResponse(success=False,message="Invalid student or course reference")
        except DataError:
            return enrollment_pb2.UploadGradeResponse(success=False,message="Invalid grade data")
        except OperationalError:
            context.abort(grpc.StatusCode.UNAVAILABLE,"Primary database unavailable")

server=grpc.server(futures.ThreadPoolExecutor(max_workers=20))
enrollment_pb2_grpc.add_GradeServiceServicer_to_server(Grades(),server)
server.add_insecure_port("[::]:50053")
server.start(); server.wait_for_termination()
