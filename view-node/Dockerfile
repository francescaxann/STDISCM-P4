FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir flask grpcio grpcio-tools psycopg2-binary pyjwt
COPY view-node/ /app/view-node/
COPY proto/ /app/proto/
COPY common/ /app/common/
RUN mkdir -p /app/generated && python -m grpc_tools.protoc -I/app/proto --python_out=/app --grpc_python_out=/app /app/proto/enrollment.proto
ENV PYTHONPATH=/app
EXPOSE 8080
CMD ["python","view-node/app.py"]
