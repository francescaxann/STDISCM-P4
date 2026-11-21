FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir grpcio grpcio-tools psycopg2-binary
COPY audit-node/ /app/audit-node/
COPY proto/ /app/proto/
COPY common/ /app/common/
RUN python -m grpc_tools.protoc -I/app/proto --python_out=/app --grpc_python_out=/app /app/proto/enrollment.proto
ENV PYTHONPATH=/app
EXPOSE 50054
CMD ["python","audit-node/server.py"]
