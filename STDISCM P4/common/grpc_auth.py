import os
import jwt
import grpc

PUBLIC_KEY = os.getenv("JWT_PUBLIC_KEY", "/app/auth-node/keys/public.pem")


def load_public_key():
    with open(PUBLIC_KEY, "rb") as fh:
        return fh.read()


class JWTServerInterceptor(grpc.ServerInterceptor):
    def intercept_service(self, continuation, handler_call_details):
        handler = continuation(handler_call_details)
        if handler is None:
            return None
        method = handler_call_details.method
        if method.endswith("/Login") or method.endswith("/Logout") or method.endswith("/ValidateToken"):
            return handler

        metadata = dict(handler_call_details.invocation_metadata())
        authorization = metadata.get("authorization", "")
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            return handler._replace(
                unary_unary=lambda request, context: context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing JWT")
            )
        try:
            claims = jwt.decode(token, load_public_key(), algorithms=["RS256"])
        except Exception:
            return handler._replace(
                unary_unary=lambda request, context: context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid JWT")
            )

        if not handler.unary_unary:
            return handler

        original = handler.unary_unary

        def authenticated(request, context):
            context.identity = {"user_id": claims["sub"], "role": claims["role"]}
            return original(request, context)

        return handler._replace(unary_unary=authenticated)


def verified_identity(context):
    metadata = dict(context.invocation_metadata())
    authorization = metadata.get("authorization", "")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        return None
    try:
        claims = jwt.decode(token, load_public_key(), algorithms=["RS256"])
        return {"user_id": claims["sub"], "role": claims["role"]}
    except Exception:
        return None


def auth_metadata(token):
    return (("authorization", f"Bearer {token}"),)
