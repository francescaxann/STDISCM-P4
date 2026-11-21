import os
import grpc
import enrollment_pb2
import enrollment_pb2_grpc

_shared_channel = None
_shared_stub = None


def audit_stub():
    global _shared_channel, _shared_stub
    if _shared_stub is None:
        host = os.getenv("AUDIT_HOST", "audit-node")
        _shared_channel = grpc.insecure_channel(host + ":50054", options=[
            ("grpc.max_reconnect_backoff_ms", 1000),
        ])
        _shared_stub = enrollment_pb2_grpc.AuditServiceStub(_shared_channel)
    return _shared_stub


def audit_event(event_type, actor_id, details):
    try:
        audit_stub().LogEvent(
            enrollment_pb2.AuditEvent(event_type=event_type, actor_id=actor_id, details=details),
            timeout=0.5,
        )
    except Exception:
        pass
