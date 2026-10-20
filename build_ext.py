import os
import sys
from pathlib import Path
from grpc_tools import protoc
import importlib.resources as res
from setup import get_ext_modules


_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def compile_protos():
    project_root = Path(__file__).parent.absolute()
    
    pb_dir = project_root / "bt_protocol" / "serialize" / "pb"
    proto_file = "bt_protocol_service.proto"
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
    grpc_path = os.path.join(proto_dir, "bt_protocol_service_pb2_grpc.py")
    if os.path.exists(grpc_path):
        with open(grpc_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # 'import bt_service_pb2 as bt__service__pb2' 
        old_imp = "import bt_protocol_service_pb2 as bt__protocol__service__pb2"
        new_imp = "from . import bt_protocol_service_pb2 as bt__protocol__service__pb2"
        if old_imp in content and new_imp not in content:
            content = content.replace(old_imp, new_imp)
            with open(grpc_path, 'w', encoding='utf-8') as f:
                f.write(content)
        if new_imp not in content:
            raise RuntimeError(
                f"Failed to patch relative import in {grpc_path}; "
                f"expected {new_imp!r} after patching."
            )

def build(setup_kwargs): # poetry build / backend setuptools
    compile_protos()

    setup_kwargs.update({
        "ext_modules": get_ext_modules()
    })


if __name__ == "__main__":
    # manual python build.py
    compile_protos()
