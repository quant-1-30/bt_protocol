# bt-protocol

> 量化回测 / 交易系统的底层通信协议层与数据 schema 定义库。

## 1. 项目概述

`bt-protocol` 是一个 Python 包（`pip install bt-protocol`，导入名 `bt_protocol`），定位为量化回测/交易系统的**协议层与 schema 定义库**。它本身不包含服务运行时，而是为消费方服务提供：

| 职责 | 技术 |
|------|------|
| 服务间消息结构（请求 / 响应） | `msgspec.msgpack` tagged union |
| gRPC 数据流接口 IDL | protobuf (`btDataFeed` service) |
| 数据库 ORM 模型 | SQLAlchemy 2.0 (`Mapped` + `mapped_column`) |
| 数据库迁移管理 | Alembic（asyncpg 异步，三分支） |
| Parquet 行情查询模板 | DuckDB SQL 字符串模板 |
| 备用序列化 schema | Avro `.avsc` / FlatBuffers `.fbs`（仅 IDL） |

- **版本**：`0.2.6`
- **Python**：`>=3.11, <3.14`
- **许可证**：GPL v3

---

## 2. 快速开始

### 2.1 安装

```bash
poetry install                    # 安装依赖
poetry install --with dev         # 含 pytest
```

### 2.2 验证导入

```bash
poetry run python -c "from bt_protocol import Event, __version__; print(__version__)"
# 0.2.6
```

### 2.3 运行测试

```bash
poetry run pytest -v
# 26 passed in 0.4s
```

### 2.4 首次数据库迁移

```bash
# 必须通过环境变量注入数据库连接字符串（alembic.ini 不再存储凭据）
export DATABASE_URL="postgresql+asyncpg://<user>:<password>@<host>:5432/<db>"

# 升级 trade 分支（建表 + 约束）
poetry run alembic upgrade trade@head
```

---

## 3. 技术栈

| 层级 | 依赖 | 版本约束 |
|------|------|----------|
| 运行时核心 | `msgspec` | `^0.18.6` |
| gRPC | `grpcio` | `>=1.83.0,<2.0` |
| ORM | `sqlalchemy` | `^2.0.47` |
| 迁移 | `alembic` | `^1.15.1` |
| 异步 PG 驱动 | `asyncpg` | `^0.31.0` |
| greenlet | `greenlet` | `^3.5.1` |
| 构建期 | `grpcio-tools`, `Cython`, `numpy`, `pybind11`, `cmake` | 仅 `[build-system]` |

> **gRPC 版本说明**：生成代码 `bt_protocol_service_pb2_grpc.py` 在 import 时强制校验 `grpcio >= 1.83.0`。若消费方安装了更旧版本，import 阶段即 `RuntimeError`。

**Poetry 源**：

| 源 | URL | 优先级 |
|----|-----|--------|
| `tuna` | `https://pypi.tuna.tsinghua.edu.cn/simple/` | primary |

> 旧的本地明文 HTTP `devpi` 源已移除（安全/可用性风险）。

---

## 4. 架构总览

```
bt_protocol/
├── _protocol.py            ← msgspec 协议层（Struct + codec）
├── constant.py             ← RpcTopic / FactorTopic 常量
├── schema/
│   ├── trade.py            ← ORM: User / Experiment / vtOrder / OrderBit / vtPosition / vtAccount
│   └── asset.py            ← ORM: Asset / Adjustment / Rightment
├── serialize/
│   ├── pb/                 ← gRPC protobuf 定义 + 生成代码
│   ├── avro/               ← Avro schema（仅 IDL，未生成代码）
│   └── fb/                 ← FlatBuffers schema（仅 IDL）
└── template/
    └── duckdb_template.py  ← DuckDB Parquet 查询 SQL 模板
```

**数据流向**：

```
消费方服务
    │
    ├── 请求: Event(topic, body=QueryBody/RegisterBody/CashBody/OrderBody)
    │        → encode_event() → msgpack bytes → 网络
    │
    ├── 响应: msgpack bytes → decode_resp() → Resp(body=BodyItem)
    │
    ├── 行情: QuoteRequest → gRPC stream → ArrowFrame(bytes payload)
    │
    └── 持久化: ORM 模型 → asyncpg → PostgreSQL
                    ↑
              Alembic 迁移管理 schema
```

---

## 5. 核心协议层（`bt_protocol._protocol`）

### 5.1 请求体（tagged union，`tag` 字段自动分派）

| Struct | tag | 字段 |
|--------|-----|------|
| `QueryBody` | `"query"` | `start_date: int`, `end_date: int`, `sid: List[bytes]` |
| `RegisterBody` | `"register"` | `client_id: bytes`, `strategy: str`, `extra_info: str` |
| `CashBody` | `"cash"` | `session: int`, `cash: float` |
| `OrderBody` | `"order"` | `sid, order_id: bytes`, `order_type, exec_type: int`, `sizer_ratio, price: float`, `created_dt: int`, `filler: Literal["default","vwap","twap"]` |

```python
# 示例
from bt_protocol import Event, QueryBody, encode_event, decode_event

ev = Event(topic=1, body=QueryBody(start_date=20200101, end_date=20201231, sid=[b"A", b"B"]))
blob = encode_event(ev)          # bytes → 网络
back = decode_event(blob)        # Event(body=QueryBody(...))
```

> `QueryBody.sid` 使用 `msgspec.field(default_factory=list)`（非裸 `[]`），避免可变默认值陷阱。

### 5.2 响应体（tagged union）

| Struct | tag | 用途 |
|--------|-----|------|
| `ExperimentBody` | `"experiment"` | 实验注册确认 |
| `TradeBody` | `"trade"` | 单笔成交回报 |
| `PositionBody` | `"position"` | 持仓快照 |
| `AccountBody` | `"account"` | 账户快照 |
| `SnapshotBody` | `"snapshot"` | 组合快照（account + positions + trades） |
| `Empty` | `"empty"` | 无数据确认 |
| `ErrMSg` | `"error"` | 错误回报（`error: str`） |
| `Sentinel` | `"sentinel"` | 流结束标记 |

```python
from bt_protocol import Resp, AccountBody, encode_resp, decode_resp

resp = Resp(body=AccountBody(
    datetime=1, portfolio_value=2.0, cash=3.0, pnl=4.0,
    leverage=1.0, margin=0.0, experiment_id=b"\x01" * 16
))
blob = encode_resp(resp)
back = decode_resp(blob)
```

### 5.3 公开 Codec API

| 函数 | 签名 | 说明 |
|------|------|------|
| `encode_event` | `(event: Event) -> bytes` | 编码请求 |
| `decode_event` | `(data: bytes) -> Event` | 解码请求 |
| `encode_resp` | `(resp: Resp) -> bytes` | 编码单条响应 |
| `decode_resp` | `(data: bytes) -> Resp` | 解码单条响应 |
| `encode_resp_list` | `(resps: List[Resp]) -> bytes` | 编码响应列表 |
| `decode_resp_list` | `(data: bytes) -> List[Resp]` | 解码响应列表 |

> 所有 codec 函数委托给模块级单例（`_ENCODER` / `_DECODER` / `_RespDECODER` / `_RespListDECODER`），msgspec 的 Encoder/Decoder **设计为线程安全可复用**，高并发下无需额外加锁。

### 5.4 线程安全与不可变性

- 所有 `msgspec.Struct` 均设 `frozen=True`，跨线程安全共享，无状态泄漏。
- `__version__` 通过 `importlib.metadata.version("bt-protocol")` 暴露，便于集群版本校验。

---

## 6. ORM 模型层（`bt_protocol.schema`）

### 6.1 trade 模型（`schema/trade.py`）

| 模型 | 表名 | 关键约束 |
|------|------|----------|
| `User` | `user_info` | 复合 PK `(id, user_id, client_id)`；`client_id` UUID `gen_random_uuid()` |
| `Experiment` | `experiment` | PK `id`；UQ `(client_id, strategy, extra_info)`；`experiment_id` UUID |
| `vtOrder` | `vtorder` | PK `id`；UQ `(order_id, experiment_id)`；UQ `order_id`（单列，供 FK 引用） |
| `OrderBit` | `order_bit` | PK `id`；FK `order_id → vtorder.order_id`；UQ `(order_id, executed_dt)` |
| `vtPosition` | `vtposition` | PK `id`；UQ `(datetime, sid, experiment_id)` |
| `vtAccount` | `account` | PK `id`；UQ `(datetime, experiment_id)` |

**关系加载策略**：所有 `relationship` 显式设为 `lazy="raise"`，禁止隐式延迟加载：

- **原因**：默认 `lazy="select"` 在 async（asyncpg）场景下会触发同步 IO，抛 `MissingGreenlet`，高并发下导致 greenlet 泄漏与 N+1 查询。
- **消费方**：需显式使用 `selectinload` / `joinedload` 控制加载策略。

**序列化方法**：

```python
# 所有模型提供 serialize() -> Resp（不是 dict）
exp = await session.get(Experiment, 1)
resp = exp.serialize()   # Resp(body=ExperimentBody(experiment_id=b"..."))
```

**`to_dict()` 性能优化**：`Base.to_dict()` 使用 `__columns__` 类层缓存（`_refresh_columns()`），避免高并发批量序列化时反复 `inspect(self).mapper` 反射。

### 6.2 asset 模型（`schema/asset.py`）

| 模型 | 表名 | 关键约束 |
|------|------|----------|
| `Asset` | `asset` | 复合 PK `(id, sid)`；`sid` / `name` 为 `LargeBinary` |
| `Adjustment` | `adjustment` | FK `sid → asset.sid`；UQ `(sid, report_date)` |
| `Rightment` | `rightment` | FK `sid → asset.sid`；UQ `(sid, ex_date)` |

---

## 7. gRPC 服务（`bt_protocol.serialize.pb`）

**服务名**：`bt.protocol.btDataFeed`

| 方法 | 请求 | 响应 | 说明 |
|------|------|------|------|
| `CalendarCall` | `QuoteRequest` | `stream ArrowFrame` | 交易日历 |
| `InstrumentCall` | `QuoteRequest` | `stream ArrowFrame` | 标的元数据 |
| `DailyStreamCall` | `QuoteRequest` | `stream ArrowFrame` | 日 K 线 |
| `TickStreamCall` | `QuoteRequest` | `stream ArrowFrame` | Tick 数据 |
| `CloseStreamCall` | `QuoteRequest` | `stream ArrowFrame` | 收盘价 |
| `AdjustmentStreamCall` | `QuoteRequest` | `stream ArrowFrame` | 除权除息 |
| `RightStreamCall` | `QuoteRequest` | `stream ArrowFrame` | 配股/增发 |
| `HeartBeat` | `google.protobuf.Empty` | `google.protobuf.Empty` | 心跳 |

```protobuf
message QuoteRequest { int32 start_date = 1; int32 end_date = 2; repeated bytes sid = 3; }
message ArrowFrame   { bytes payload = 1; }
```

**编译**：

```bash
python build_ext.py    # 编译 .proto → _pb2.py / _pb2_grpc.py / _pb2.pyi
```

---

## 8. 数据库迁移（Alembic）

### 8.1 三分支结构

```
feed 分支:
  28cdc82de517 (None, branch='feed')
    └─ 616545e13eb4 (head)

trade 分支:
  a0b1c2d3e4f5 (None)              ← 建表根（user_info / experiment / vtorder / order_bit / vtposition / account）
    └─ 30aae0684ec1 (branch='trade')  ← drop old UQ + create uq_order_id_experiment_id
         └─ 542a904f887a              ← drop order_bit_order_id_key (IF EXISTS)
              └─ 95eb41d7a5ac          ← add created_dt on vtposition
                   └─ f1a2b3c4d5e6 (head)  ← CREATE UNIQUE INDEX IF NOT EXISTS uq_vtorder_order_id

asset 分支:
  70e341d5e7a8 (None)
    └─ 79a49578303d (head)
```

### 8.2 DATABASE_URL 强制注入

`alembic.ini` 中 `sqlalchemy.url =` 为空，**不存储任何凭据**。`env.py` 在 `DATABASE_URL` 环境变量缺失时直接 `raise RuntimeError`：

```bash
# 正确用法
export DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/db"
poetry run alembic upgrade trade@head

# 不设置 DATABASE_URL → RuntimeError
```

### 8.3 常用命令

```bash
poetry run alembic heads              # 查看所有 head
poetry run alembic history --verbose  # 查看完整迁移链
poetry run alembic upgrade trade@head # 升级 trade 分支
poetry run alembic downgrade -1       # 回退一步
```

---

## 9. 性能与安全

### 9.1 性能（审计确认无泄漏）

| 检查项 | 状态 | 说明 |
|--------|------|------|
| codec 单例线程安全 | ✅ 正确 | msgspec Encoder/Decoder 模块级单例，无需锁 |
| `frozen=True` 不可变 | ✅ 正确 | 跨线程安全共享 |
| `to_dict()` 列缓存 | ✅ 已优化 | `__columns__` 类层缓存避免反复反射 |
| per-message codec 分配 | ✅ 无 | 吞吐基准 > 50k round-trips/s |
| 连接池泄漏 | ✅ 无 | 迁移使用 `NullPool`（用完即弃） |

### 9.2 安全（已整改）

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 数据库凭据 | ✅ 已清理 | `alembic.ini` 留空，强制 `DATABASE_URL` 注入 |
| 明文 HTTP 源 | ✅ 已移除 | `devpi` 本地源删除 |
| SQL 注入 | ✅ 无风险 | DuckDB 模板全参数化（`?` 占位） |
| greenlet 泄漏 | ✅ 已修复 | `lazy="raise"` 禁止 async 场景隐式 IO |

> **历史口令提醒**：git 历史中曾出现明文口令（`20210718` / `postgres`）。本次仅清理工作区，未重写历史。请轮换所有曾在该仓库出现过的数据库口令。

---

## 10. 测试与开发

### 10.1 测试覆盖（26 用例）

| 类别 | 用例 | 说明 |
|------|------|------|
| Avro schema | 4 | `.avsc` 文件存在 + JSON 合法 |
| 公开 API | 2 | 导入完整性 + `__version__` |
| msgspec round-trip | 8 | Event 请求 + Resp 各 Body |
| gRPC 导入 | 1 | `_pb2_grpc` 在 `grpcio>=1.83.0` 下不报错 |
| FK 唯一性 | 1 | `vtorder.order_id` 单列 UQ 存在 |
| lazy 策略 | 1 | 所有 `relationship` 禁止默认 `select` |
| 凭据检查 | 1 | `alembic.ini` 不含明文 |
| 吞吐基准 | 1 | encode+decode > 5000 round-trips/s |
| 类型契约 | 1 | `serialize()` 返回注解为 `Resp` |
| Resp 列表 | 2 | 列表 round-trip + None body |

```bash
poetry run pytest -v
```

### 10.2 开发

```bash
# 编译 protobuf（手动）
python build_ext.py

# 构建 wheel
poetry build

# setuptools 本地开发
python setup.py build_ext --inplace
```

### 10.3 常用命令速查

```bash
poetry install                           # 安装依赖
poetry run pytest -v                     # 运行测试
python build_ext.py                      # 编译 protobuf
poetry build                             # 构建 wheel
export DATABASE_URL=...                  # 设置数据库连接
poetry run alembic upgrade trade@head    # 迁移
poetry run alembic heads                 # 查看分支 head