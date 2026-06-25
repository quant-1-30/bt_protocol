## 1. 项目概述

`bt-protocol` 是一个 Python 包，定位为量化回测/交易系统的协议层与数据 schema 定义库。核心职责包括：

- 定义服务间通信的消息结构（基于 `msgspec` 的 msgpack 编解码）。
- 提供 gRPC 数据服务接口定义（`bt_protocol/serialize/pb/service.proto`），并在构建时自动生成 Python 桩代码。
- 定义 SQLAlchemy ORM 模型，用于资产元数据（`asset/adjustment/rightment`）和交易记录（`experiment/order/position/account`）。
- 通过 Alembic 管理 PostgreSQL 数据库迁移。
- 保留 Avro / FlatBuffers schema 文件作为历史/备用序列化方案

包名：`bt-protocol`（PyPI/内部 Wheel 名称），导入名：`bt_protocol`。当前 `pyproject.toml` 中版本为 `0.2.1`（工作区未提交修改）。许可证：GNU General Public License v3（见 `LICENSE`）。

---

## 2. 技术栈

| 层级 | 技术 |
|------|------|
| 语言 | Python >=3.11, <3.15 |
| 包管理 / 构建 | Poetry（`pyproject.toml` + `poetry.lock`） |
| 运行时依赖 | `grpcio`, `sqlalchemy`, `alembic`, `asyncpg`, `greenlet` |
| 实际使用但未声明的依赖 | `msgspec`（见第 9 节“已知问题”）、`protobuf`（由 `grpcio` 隐式引入） |
| 序列化 | `msgspec.msgpack`（核心协议）、gRPC/protobuf（数据流接口）、Avro/FlatBuffers schema（仅定义） |
| 数据库 | PostgreSQL + asyncpg，通过 Alembic 异步迁移 |
| 可选构建扩展 | Cython / pybind11 / CMake（当前 `build_ext.py` 中无实际扩展，仅保留骨架） |

Poetry 配置了两条源：

- `tuna`（主源）：`https://pypi.tuna.tsinghua.edu.cn/simple/`
- `devpi`（补充源）：`http://localhost:3141/bt_sdk/dev/+simple/`

> 注意：`devpi` 指向 `localhost`，在 CI 或外部机器上安装可能失败。

---

## 3. 目录结构

```
bt-protocol/
├── pyproject.toml              # Poetry 项目配置、依赖、构建脚本
├── poetry.lock                 # 锁定依赖版本
├── setup.py                    # setuptools 入口，用于本地扩展模块开发/调试
├── build_ext.py                # 构建钩子：编译 .proto 并生成 Cython/pybind11 扩展
├── alembic.ini                 # Alembic 配置（含数据库 URL）
├── alembic/                    # 迁移脚本目录
│   ├── env.py                  # 异步迁移环境
│   ├── script.py.mako          # 迁移文件模板
│   └── versions/               # 历史迁移脚本
├── bt_protocol/                # 主包
│   ├── __init__.py             # 空文件
│   ├── _protocol.py            # msgspec 消息结构定义（Event / Resp / 各类 Body）
│   ├── constant.py             # RpcTopic / FactorTopic 常量
│   ├── schema/
│   │   ├── asset.py            # Asset / Adjustment / Rightment ORM 模型
│   │   └── trade.py            # User / Experiment / vtOrder / OrderBit / vtPosition / vtAccount ORM 模型
│   ├── serialize/
│   │   ├── pb/                 # protobuf 定义与生成代码
│   │   │   ├── service.proto
│   │   │   ├── service_pb2.py
│   │   │   ├── service_pb2.pyi
│   │   │   └── service_pb2_grpc.py
│   │   ├── avro/               # Avro schema（未生成代码）
│   │   └── fb/                 # FlatBuffers schema（未生成代码）
│   └── template/
│       └── duckdb_template.py  # DuckDB parquet 查询模板字符串
├── tests/
│   └── __init__.py             # 空文件，当前无测试用例
├── README.md                   # 个人笔记（多为中文 git/PostgreSQL 操作备忘）
└── LICENSE                     # GPL v3
```

---

## 4. 构建与打包

### 4.1 安装依赖

```bash
poetry install
```

如果需要开发依赖，目前 `pyproject.toml` 中未定义任何 dev group，因此 `poetry install --with dev` 无效。

### 4.2 编译 protobuf

在 Poetry 构建过程中，`build_ext.py` 会自动调用 `grpc_tools.protoc` 编译 `bt_protocol/serialize/pb/service.proto`，并自动补丁 `service_pb2_grpc.py` 中的相对导入：

```python
# 由 build_ext.py patch_grpc_imports 自动完成
import service_pb2 as service__pb2    # 原生成结果
from . import service_pb2 as service__pb2  # 补丁后
```

手动编译命令（参考）：

```bash
python -m grpc_tools.protoc \
  -I bt_protocol/serialize/pb \
  -I $(python -c "import importlib.resources, grpc_tools; print(importlib.resources.files('grpc_tools').joinpath('_proto'))") \
  --python_out=bt_protocol/serialize/pb \
  --grpc_python_out=bt_protocol/serialize/pb \
  --pyi_out=bt_protocol/serialize/pb \
  bt_protocol/serialize/pb/service.proto
```

或直接运行：

```bash
python build_ext.py
```

### 4.3 构建 Wheel / sdist

```bash
poetry build
```

`pyproject.toml` 的 `include` 规则显式包含 protobuf 生成文件、`.pyi`、`.pyx` 和 `.so`，确保它们进入分发包。`grpcio-tools` 只在 `[build-system] requires` 中，不作为运行时依赖。

### 4.4 本地 setuptools 开发

```bash
python setup.py build_ext --inplace
```

当前 `build_ext.py` 中 `extensions` 列表为空（全部注释掉），因此不会产生任何 `.so`。

---

## 5. 数据库迁移

项目使用 Alembic + SQLAlchemy 2.0 + asyncpg。迁移入口：

```bash
poetry run alembic upgrade head
poetry run alembic downgrade -1
poetry run alembic revision --autogenerate -m "describe change"
```

### 5.1 数据库连接

`alembic.ini` 中硬编码了：

```ini
sqlalchemy.url = postgresql+asyncpg://postgres:20210718@localhost:5432/bt_feed
```

生产或共享环境必须修改此 URL，避免泄露密码。`alembic/env.py` 使用 `async_engine_from_config` 异步执行迁移，`target_metadata = None`，因此**不支持 autogenerate**（需要手动写迁移脚本）。

### 5.2 迁移分支结构

当前 `alembic/versions/` 下有三个独立分支（无合并）：

| 分支 | 迁移链 | 说明 |
|------|--------|------|
| `feed` | `28cdc82de517` → `616545e13eb4` | 资产元数据：sid/name 由 str 改为 bytes，字段非空约束调整 |
| `trade` | `30aae0684ec1` → `a28c60594937`（文件名 `542a904f887a...`） → `95eb41d7a5ac` | 交易相关表：vtorder 唯一约束、order_bit 唯一约束、vtposition 增加 created_dt |
| `asset` | `70e341d5e7a8` → `79a49578303d` | asset 表增加 merger/ratio 字段、delist 改为 nullable |

> 注意：`542a904f887a_revise_unqiue_order_id_in_order_bit.py` 文件内的 `revision` 变量实际为 `a28c60594937`，与文件名不一致，且文件内存在重复 docstring。这是已存在的内容缺陷，修改前需先理顺 Alembic 版本链。

---

## 6. 代码组织与主要模块

### 6.1 核心消息协议 `bt_protocol._protocol`

所有数据结构均为 `msgspec.Struct`，`frozen=True`，请求侧通过 `tag` 字段实现 tagged union。主要类型：

- 请求：`Event` 包含 `topic`, `sub_topic`, `experiment_id`, `body`，`body` 为 `QueryBody / RegisterBody / CashBody / OrderBody` 的 Union。
- 响应：`Resp` 包含 `body`，可为 `ExperimentBody / TradeBody / PositionBody / AccountBody / SnapshotBody / Empty / ErrMSg / Sentinel` 或其列表。
- 全局编解码器：`_ENCODER = msgspec.msgpack.Encoder()`、`_DECODER = msgspec.msgpack.Decoder(type=Event)`、`_RespDECODER`。

### 6.2 ORM 模型

- `bt_protocol.schema.asset`：
  - `Asset`：资产主表，复合主键 `(id, sid)`，sid/name 为 `LargeBinary`。
  - `Adjustment`：除权除息，外键 `asset.sid`。
  - `Rightment`：配股/增发，外键 `asset.sid`。
- `bt_protocol.schema.trade`：
  - `User`（`user_info` 表）、`Experiment`：实验/策略注册。
  - `vtOrder`、`OrderBit`：订单与成交明细。
  - `vtPosition`、`vtAccount`：持仓与账户快照。

表名使用小写：`asset`, `adjustment`, `rightment`, `user_info`, `experiment`, `vtorder`, `order_bit`, `vtposition`, `account`。

### 6.3 gRPC 服务 `bt_protocol.serialize.pb`

服务名 `btDataFeed`，所有方法均为 `unary_stream`，返回 `ArrowFrame`（payload 为 bytes）：

- `CalendarCall`
- `InstrumentCall`
- `DailyStreamCall`
- `TickStreamCall`
- `CloseStreamCall`
- `AdjustmentStreamCall`
- `RightStreamCall`
- `HeartBeat`

### 6.4 模板与备用 schema

- `bt_protocol.template.duckdb_template.py`：包含 `TICK_TEMPLATE`、`CLOSE_TEMPLATE`、`DAILY_TEMPLATE`，用于从 parquet 读取 tick/日 K/收盘价数据。
- `serialize/avro/*.avsc`、`serialize/fb/bt_service.fbs`：仅保留 schema 文本，未生成 Python 类，也未被主代码引用。

---

## 7. 代码风格与约定

- 文件头习惯写 `#!/usr/bin/env python3` 和 `# -*- coding: utf-8 -*-`。
- 注释大量使用中文；变量/类名为英文。
- SQLAlchemy 使用 2.0 风格：`Mapped[...]` + `mapped_column(...)`。
- 主键/唯一约束、外键级联行为在模型中显式声明。
- `__all__` 在 `asset.py` 和 `trade.py` 底部导出公开名称。
- `serialize` 子目录下均放置 `__init__.py`，即使为空，也确保作为包被包含。

---

## 8. 测试策略

当前项目**没有测试用例**。`tests/` 目录下仅包含空的 `__init__.py`。

建议后续补充：

- `msgspec` 消息序列化/反序列化 round-trip 测试。
- ORM 模型字段与约束的基本冒烟测试。
- protobuf 生成文件能否正常导入的测试。
- Alembic 迁移脚本在本地/测试数据库上的 `upgrade`/`downgrade` 测试。

临时验证导入：

```bash
poetry run python -c "from bt_protocol._protocol import Event; print('ok')"
```

当前会因缺少 `msgspec` 而失败（见第 9 节）。

---

## 9. 部署与发布

- 本地/开发：使用 `poetry install` + `poetry run alembic upgrade head`。
- 打包：`poetry build` 生成 wheel/sdist 到 `dist/`。
- 当前未配置 CI/CD（无 `.github/workflows/`、无 GitLab CI、无 pre-commit）。
- 若发布到私有仓库，注意 `pyproject.toml` 中的 `devpi` 源配置；发布前建议移除或改用环境变量配置源。

---

## 10. 安全与重要注意事项

1. **数据库凭据硬编码**：`alembic.ini` 中明文包含 PostgreSQL 密码 `postgresql+asyncpg://postgres:20210718@localhost:5432/bt_feed`。任何修改都应避免将真实密码提交到仓库。
2. **依赖缺失**：`msgspec` 被 `_protocol.py` 直接导入，但未在 `pyproject.toml` 的 `dependencies` 中声明。当前虚拟环境中也未安装，导致包无法导入。必须添加 `msgspec = "^..."` 到 `[tool.poetry.dependencies]` 并执行 `poetry lock --no-cache`。
3. **本地 devpi 源**：`http://localhost:3141/...` 源在 CI/CD 或他人机器上不可用，且为明文 HTTP。
4. **迁移脚本异常**：`542a904f887a_revise_unqiue_order_id_in_order_bit.py` 存在内部 revision ID 与文件名不一致的问题，运行 `alembic history`/`upgrade` 前可能需要修复。
5. **Avro/FlatBuffers schema 未生成代码**：这些文件目前只是文档/IDL，修改后不会自动同步到运行时。
6. **未提交的本地修改**：截至当前工作区，`pyproject.toml` 和 `bt_protocol/_protocol.py` 有未提交改动（版本号、OrderBody 字段 `pricelimit` → `price`）。写新代码前建议先 `git diff` 确认。

---

## 11. 常用命令速查

```bash
# 安装依赖
poetry install

# 编译 protobuf（手动）
python build_ext.py

# 构建 wheel
poetry build

# 数据库迁移
poetry run alembic upgrade head
poetry run alembic history
poetry run alembic revision -m "migration message"

# 验证导入（修复 msgspec 依赖后）
poetry run python -c "from bt_protocol._protocol import Event; print('ok')"
```

---
