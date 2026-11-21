import os, time, uuid, hashlib
from concurrent import futures
import grpc, jwt
import enrollment_pb2, enrollment_pb2_grpc
import sys
sys.path.append('/app')
from common.db import pool, connection

SECRET = os.getenv('JWT_SECRET','dev-enrollment-secret')
DB_HOST=os.getenv('DB_PRIMARY','db-primary')
pool_obj=pool(DB_HOST)

class Auth(enrollment_pb2_grpc.AuthServiceServicer):
    def Login(self, req, context):
        digest=hashlib.sha1(req.password.encode()).hexdigest()
        try:
            with connection(pool_obj) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id,role FROM users WHERE username=%s AND password_hash=%s",(req.username,digest))
                    row=cur.fetchone()
        except Exception as e:
            context.abort(grpc.StatusCode.UNAVAILABLE,'Database unavailable')
        if not row: return enrollment_pb2.LoginResponse(success=False,message='Invalid credentials')
        token=jwt.encode({'sub':row[0],'role':row[1],'jti':str(uuid.uuid4()),'exp':int(time.time())+28800},SECRET,algorithm='HS256')
        return enrollment_pb2.LoginResponse(success=True,token=token,message='Login successful')
    def Logout(self, req, context):
        try:
            claims=jwt.decode(req.token,SECRET,algorithms=['HS256'])
            with connection(pool_obj) as conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO revoked_tokens(jti,expires_at) VALUES (%s,to_timestamp(%s)) ON CONFLICT(jti) DO NOTHING",(claims['jti'],claims['exp']))
                conn.commit()
            return enrollment_pb2.LogoutResponse(success=True)
        except Exception:
            return enrollment_pb2.LogoutResponse(success=False)
    def ValidateToken(self, req, context):
        try:
            claims=jwt.decode(req.token,SECRET,algorithms=['HS256'])
            with connection(pool_obj) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM revoked_tokens WHERE jti=%s",(claims['jti'],))
                    if cur.fetchone(): raise ValueError('revoked')
            return enrollment_pb2.ValidateResponse(valid=True,user_id=claims['sub'],role=claims['role'])
        except Exception:
            return enrollment_pb2.ValidateResponse(valid=False)

server=grpc.server(futures.ThreadPoolExecutor(max_workers=10))
enrollment_pb2_grpc.add_AuthServiceServicer_to_server(Auth(),server)
server.add_insecure_port('[::]:50051')
server.start(); server.wait_for_termination()
