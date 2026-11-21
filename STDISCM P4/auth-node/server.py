import os, time, uuid
from concurrent import futures
import grpc, jwt, bcrypt
import enrollment_pb2, enrollment_pb2_grpc
from common.db import pool, connection, LazyReplicaPool
from common.grpc_auth import JWTServerInterceptor

DB_PRIMARY=os.getenv("DB_PRIMARY","db-primary")
DB_REPLICA=os.getenv("DB_REPLICA","db-replica")
private_key=open(os.getenv("JWT_PRIVATE_KEY","/app/auth-node/keys/private.pem"),"rb").read()
public_key=open(os.getenv("JWT_PUBLIC_KEY","/app/auth-node/keys/public.pem"),"rb").read()
primary=pool(DB_PRIMARY)
replica=LazyReplicaPool(DB_REPLICA)

class Auth(enrollment_pb2_grpc.AuthServiceServicer):
    def Login(self, req, context):
        selected=replica.get()
        try:
            if selected:
                try:
                    with connection(selected) as conn:
                        with conn.cursor() as cur:
                            cur.execute("SELECT id,password_hash,role FROM users WHERE username=%s",(req.username,))
                            row=cur.fetchone()
                except Exception:
                    replica.pool=None
                    selected=None
            if not selected:
                with connection(primary) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT id,password_hash,role FROM users WHERE username=%s",(req.username,))
                        row=cur.fetchone()
        except Exception:
            context.abort(grpc.StatusCode.UNAVAILABLE,"Database unavailable")
        if not row or not bcrypt.checkpw(req.password.encode(), row[1].encode() if isinstance(row[1],str) else row[1]):
            return enrollment_pb2.LoginResponse(success=False,message="Invalid credentials")
        token=jwt.encode({"sub":row[0],"role":row[2],"jti":str(uuid.uuid4()),"exp":int(time.time())+28800},private_key,algorithm="RS256")
        return enrollment_pb2.LoginResponse(success=True,token=token,message="Login successful")

    def Logout(self, req, context):
        try:
            claims=jwt.decode(req.token,public_key,algorithms=["RS256"])
            with connection(primary) as conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO revoked_tokens(jti,expires_at) VALUES(%s,to_timestamp(%s)) ON CONFLICT(jti) DO NOTHING",(claims["jti"],claims["exp"]))
                conn.commit()
            return enrollment_pb2.LogoutResponse(success=True)
        except Exception:
            return enrollment_pb2.LogoutResponse(success=False)

    def ValidateToken(self, req, context):
        try:
            claims=jwt.decode(req.token,public_key,algorithms=["RS256"])
        except jwt.PyJWTError:
            return enrollment_pb2.ValidateResponse(valid=False)
        revoked=None
        for p in (primary, replica.get()):
            if p is None:
                continue
            try:
                with connection(p) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1 FROM revoked_tokens WHERE jti=%s",(claims["jti"],))
                        revoked=cur.fetchone() is not None
                break
            except Exception:
                if p is not primary:
                    replica.pool=None
        if revoked is None:
            # DB unreachable: say so, so the view falls back to local JWT verification
            context.abort(grpc.StatusCode.UNAVAILABLE,"Revocation list unavailable")
        if revoked:
            return enrollment_pb2.ValidateResponse(valid=False)
        return enrollment_pb2.ValidateResponse(valid=True,user_id=claims["sub"],role=claims["role"])

server=grpc.server(futures.ThreadPoolExecutor(max_workers=10),interceptors=(JWTServerInterceptor(),))
enrollment_pb2_grpc.add_AuthServiceServicer_to_server(Auth(),server)
server.add_insecure_port("[::]:50051")
server.start(); server.wait_for_termination()
