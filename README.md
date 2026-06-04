# python -m grpc_tools.protoc -I . --python_out=. --pyi_out=. --grpc_python_out=. service.proto 

#### 1. 修正 `bt-protocol/pyproject.toml` (最关键)

`grpcio-tools` 是一个 **编译器（Compiler）**。它的作用是把 `.proto` 变成 `.py`。一旦编译完成，代码运行只需要 `grpcio` 和 `protobuf` 库，**不需要** `grpcio-tools`。

你误把编译器放进了 `dependencies`（运行时依赖），导致每个安装 `bt-protocol` 的项目都被迫去安装这个编译器，从而引发版本锁死。

**请修改 `bt-protocol/pyproject.toml`：**


main ---> dev

git checkout dev / git fetch origin / git merge origin/main / git add .  and commit and solve conflicts / git push origin dev

rebase

git checkout dev / git fetch origin / git rebase origin main / git add . and git rebase --continue not need commit / git push origin dev --force-with-lease
