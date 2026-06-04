import os
import sys
import glob

import subprocess
from pathlib import Path
from grpc_tools import protoc
import importlib.resources as res
from setup import get_ext_modules


def compile_protos():
    project_root = Path(__file__).parent.absolute()
    
    pb_dir = project_root / "bt_protocol" / "serialize" / "pb"
    proto_file = "bt_service.proto"
    proto_path = pb_dir / proto_file

    # google/protobuf/empty.proto
    proto_include = str(res.files("grpc_tools").joinpath("_proto"))

    if not proto_path.exists():
        print(f"❌ Error: Proto file not found at {proto_path}")
        sys.exit(1)

    (pb_dir / "__init__.py").touch(exist_ok=True)

    print(f"🔨 Compiling protobuf: {proto_file} inside {pb_dir.relative_to(project_root)} ...")

    args = [
        "grpc_tools.protoc",
        f"-I{pb_dir}", 
        f"-I{proto_include}",    
        f"--python_out={pb_dir}",
        f"--grpc_python_out={pb_dir}",
        f"--pyi_out={pb_dir}",
        str(proto_path)
    ]

    #  protoc.main first placehold
    if protoc.main(args) != 0:
        print("❌ Error: Protobuf compilation failed")
        sys.exit(1)
   
    patch_grpc_imports(pb_dir)
    print("✅ Protobuf compilation completed successfully.")

   
def patch_grpc_imports(proto_dir):
    grpc_path = os.path.join(proto_dir, "bt_service_pb2_grpc.py")
    if os.path.exists(grpc_path):
        with open(grpc_path, 'r') as f:
            content = f.read()
        # 'import bt_service_pb2 as bt__service__pb2' 
        old_imp = "import bt_service_pb2 as bt__service__pb2"
        new_imp = "from . import bt_service_pb2 as bt__service__pb2"
        if old_imp in content:
            with open(grpc_path, 'w') as f:
                f.write(content.replace(old_imp, new_imp))

def build(setup_kwargs): # poetry build / backend setuptools
    compile_protos()

    setup_kwargs.update({
        "ext_modules": get_ext_modules()
    })


if __name__ == "__main__":
    # manual python build.py
    compile_protos()
