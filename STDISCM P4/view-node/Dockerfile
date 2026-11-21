FROM enrollment-base:local AS builder
RUN pip install --no-cache-dir grpcio-tools==1.76.0
COPY proto/ /app/proto/
RUN python -m grpc_tools.protoc -I/app/proto --python_out=/app --grpc_python_out=/app /app/proto/enrollment.proto

FROM enrollment-base:local
WORKDIR /app
COPY --from=builder /app/enrollment_pb2.py /app/enrollment_pb2.py
COPY --from=builder /app/enrollment_pb2_grpc.py /app/enrollment_pb2_grpc.py
COPY view-node/ /app/view-node/
COPY common/ /app/common/
RUN apt-get update >/dev/null 2>&1 && apt-get install -y --no-install-recommends openssl >/dev/null 2>&1 && rm -rf /var/lib/apt/lists/* || true
RUN mkdir -p /app/view-node/certs && if [ ! -f /app/view-node/certs/server.key ]; then openssl req -x509 -newkey rsa:2048 -nodes -keyout /app/view-node/certs/server.key -out /app/view-node/certs/server.crt -days 365 -subj '/CN=localhost' -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1' >/dev/null 2>&1; fi
ENV PYTHONPATH=/app
ENV JWT_PUBLIC_KEY=/app/keys/public.pem
EXPOSE 8080
CMD ["python","view-node/app.py"]
