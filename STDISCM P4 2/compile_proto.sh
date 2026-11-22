#!/usr/bin/env sh
set -e
python3 -m grpc_tools.protoc -Iproto --python_out=. --grpc_python_out=. proto/enrollment.proto
