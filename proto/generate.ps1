# Generate Python protobuf/gRPC code from proto definitions.
# Run from the proto/ directory.
python -m grpc_tools.protoc `
  --proto_path=. `
  --python_out=.. `
  --grpc_python_out=.. `
  iris/io/transport/grpc_service.proto
