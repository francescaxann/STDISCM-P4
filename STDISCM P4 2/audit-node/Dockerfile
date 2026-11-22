FROM enrollment-base:local AS builder
RUN pip install --no-cache-dir grpcio-tools==1.76.0
COPY proto/ /app/proto/
RUN python -m grpc_tools.protoc -I/app/proto --python_out=/app --grpc_python_out=/app /app/proto/enrollment.proto

FROM enrollment-base:local
WORKDIR /app
COPY --from=builder /app/enrollment_pb2.py /app/enrollment_pb2.py
COPY --from=builder /app/enrollment_pb2_grpc.py /app/enrollment_pb2_grpc.py
COPY common/ /app/common/
COPY audit-node/ /app/audit-node/
ENV PYTHONPATH=/app
ENV JWT_PUBLIC_KEY=/app/keys/public.pem
EXPOSE 50054
CMD ["python","audit-node/server.py"]
