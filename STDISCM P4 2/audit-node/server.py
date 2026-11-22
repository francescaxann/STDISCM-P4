import os
from concurrent import futures
import grpc
import enrollment_pb2
import enrollment_pb2_grpc
from common.db import pool, connection
from common.grpc_auth import verified_identity

pool_obj = pool(os.getenv("DB_PRIMARY", "db-primary"))


class Audit(enrollment_pb2_grpc.AuditServiceServicer):
    def LogEvent(self, req, context):
        try:
            with connection(pool_obj) as conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO audit_log(event_type,actor_id,details) VALUES(%s,%s,%s)",
                                (req.event_type, req.actor_id, req.details))
                conn.commit()
            return enrollment_pb2.AuditResponse(accepted=True)
        except Exception:
            context.abort(grpc.StatusCode.UNAVAILABLE, "Audit database unavailable")

    def CreateReceipt(self, req, context):
        identity = verified_identity(context)
        if not identity:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing or invalid JWT")
        try:
            student_id = identity["user_id"] if identity["role"] == "STUDENT" else req.student_id
            with connection(pool_obj) as conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO receipts(student_id,course_id,status,details) VALUES(%s,%s,%s,%s) RETURNING id",
                                (student_id, req.course_id, req.status or "CREATED", req.details))
                    receipt_id = cur.fetchone()[0]
                conn.commit()
            return enrollment_pb2.ReceiptResponse(success=True, message="Receipt created", id=receipt_id)
        except Exception:
            context.abort(grpc.StatusCode.UNAVAILABLE, "Receipt database unavailable")

    def GetReceipt(self, req, context):
        identity = verified_identity(context)
        if not identity:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Verified identity required")
        try:
            with connection(pool_obj) as conn:
                with conn.cursor() as cur:
                    if identity["role"] == "STUDENT":
                        cur.execute("SELECT id,student_id,course_id,status,details FROM receipts WHERE id=%s AND student_id=%s", (req.id, identity["user_id"]))
                    else:
                        cur.execute("SELECT id,student_id,course_id,status,details FROM receipts WHERE id=%s", (req.id,))
                    row = cur.fetchone()
            if not row:
                context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not allowed")
            return enrollment_pb2.Receipt(id=row[0], student_id=row[1], course_id=row[2], status=row[3], details=row[4] or "")
        except grpc.RpcError:
            raise
        except Exception:
            context.abort(grpc.StatusCode.UNAVAILABLE, "Receipt database unavailable")

    def ListReceipts(self, req, context):
        identity = verified_identity(context)
        try:
            with connection(pool_obj) as conn:
                with conn.cursor() as cur:
                    if identity["role"] == "STUDENT":
                        cur.execute("SELECT id,student_id,course_id,status,details FROM receipts WHERE student_id=%s ORDER BY id DESC", (identity["user_id"],))
                    else:
                        cur.execute("SELECT id,student_id,course_id,status,details FROM receipts ORDER BY id DESC")
                    rows = cur.fetchall()
            receipts = [enrollment_pb2.Receipt(id=r[0], student_id=r[1], course_id=r[2], status=r[3], details=r[4] or "") for r in rows]
            return enrollment_pb2.ReceiptList(receipts=receipts)
        except Exception:
            context.abort(grpc.StatusCode.UNAVAILABLE, "Receipt database unavailable")

    def UpdateReceipt(self, req, context):
        identity = verified_identity(context)
        if not identity:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing or invalid JWT")
        try:
            with connection(pool_obj) as conn:
                with conn.cursor() as cur:
                    if identity["role"] == "STUDENT":
                        cur.execute("UPDATE receipts SET status=%s,details=%s,updated_at=now() WHERE id=%s AND student_id=%s", (req.status, req.details, req.id, identity["user_id"]))
                    else:
                        cur.execute("UPDATE receipts SET status=%s,details=%s,updated_at=now() WHERE id=%s", (req.status, req.details, req.id))
                    if cur.rowcount == 0:
                        conn.rollback()
                        context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not allowed")
                conn.commit()
            return enrollment_pb2.ReceiptResponse(success=True, message="Receipt updated", id=req.id)
        except grpc.RpcError:
            raise
        except Exception:
            context.abort(grpc.StatusCode.UNAVAILABLE, "Receipt database unavailable")

    def DeleteReceipt(self, req, context):
        identity = verified_identity(context)
        if not identity:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing or invalid JWT")
        try:
            with connection(pool_obj) as conn:
                with conn.cursor() as cur:
                    if identity["role"] == "STUDENT":
                        cur.execute("DELETE FROM receipts WHERE id=%s AND student_id=%s", (req.id, identity["user_id"]))
                    else:
                        cur.execute("DELETE FROM receipts WHERE id=%s", (req.id,))
                    if cur.rowcount == 0:
                        conn.rollback()
                        context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not allowed")
                conn.commit()
            return enrollment_pb2.ReceiptResponse(success=True, message="Receipt deleted", id=req.id)
        except grpc.RpcError:
            raise
        except Exception:
            context.abort(grpc.StatusCode.UNAVAILABLE, "Receipt database unavailable")


server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
enrollment_pb2_grpc.add_AuditServiceServicer_to_server(Audit(), server)
server.add_insecure_port("[::]:50054")
server.start()
server.wait_for_termination()
