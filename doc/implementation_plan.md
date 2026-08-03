# bt_protocol 泄漏与高并发性能审计报告

> 本文档为 **审计报告**，依据用户要求「仅做审计报告，不改代码」。所有条目均为发现 + 证据 + 建议 remediation（**未执行**）。每条标注严重级别（CRITICAL / HIGH / MEDIUM / LOW / INFO）与影响场景。
> 审计基线 commit：`723171be48e14c2523fb981c605ae00cd32226b8`；运行时验证 msgspec `0.18.6`。

[Overview]

本审计的目标是回答："bt_protocol 作为整个服务底层通信协议，是否存在泄漏（leak）或性能泄漏，特别是在高并发场景下"。

结论一句话：**bt_protocol 本身是一个 schema/codec 定义库（msgspec 结构 + SQLAlchemy ORM + gRPC IDL + Alembic 迁移），仓库内不存在 server 运行时、线程池、连接池、缓存或后台任务，因此不存在传统意义上的"运行时资源泄漏"。但存在若干会在高并发/生产场景下触发"可用性泄漏"和"安全泄漏"的静态缺陷，必须在消费方上线前修复。**

审计方法：

1. 逐文件阅读 `bt_protocol/_protocol.py`、`bt_protocol/schema/{asset,trade}.py`、`bt_protocol/constant.py`、`bt_protocol/template/duckdb_template.py`、`bt_protocol/serialize/pb/*.proto` 及生成代码、`alembic/env.py`、全部 `alembic/versions/*.py`、`pyproject.toml`、`alembic.ini`、`setup.py`、`build_ext.py`、`tests/test_protocol.py`、`README.md`。
2. 运行时验证 msgspec 关键语义：mutable default 是否共享、`Encoder/Decoder` 是否可复用、`msgspec.field(default_factory=...)` 与 `= []` 的行为差异、`Encoder.encode_into` 是否存在。
3. 静态分析依赖矩阵：`grpcio` 运行时版本约束 vs. 生成代码的硬性版本要求；`grpcio-tools` 是否被错误地放入运行时；`devpi` 本地明文源风险。

按严重级别汇总（详见后续各节）：

| 级别 | 数量 | 代表性问题 |
|------|------|-----------|
| CRITICAL | 2 | (1) 生成 gRPC 桩代码要求 `grpcio>=1.83.0`，但 `pyproject.toml` 声明 `grpcio="^1.71.0"`，import 时即 `RuntimeError`；(2) `alembic.ini` 内硬编码数据库口令（安全泄漏）。 |
| HIGH | 2 | (1) `OrderBit.order_id` 外键指向 `vtorder.order_id` 单列，而该列并不唯一（唯一约束是 `(order_id, experiment_id)` 复合），PostgreSQL 下建表/并发写入会失败；(2) ORM 关系默认 `lazy="select"`，在 asyncpg/async 场景下触发 greenlet 同步 IO，高并发必爆。 |
| MEDIUM | 3 | `alembic/env.py` 吞 `Exception` 静默关闭 autogenerate；`serialize()` 返回 `Resp` 但标注 `-> dict`（类型契约失真）；`devpi` 本地明文 HTTP 源 + `localhost` 不可达。 |
| LOW | 6 | mutable-default 写法、`use_existing_column` 滥用、私有 codec 被公开导出、Avro schema 与 DuckDB 实际类型不一致、缺失 `__version__`、README 过期陈述。 |
| INFO | 3 | 全局 codec 线程安全（正确）、DuckDB 模板参数化（正确）、msgspec 默认值非共享（已实测）。 |

> 关于"性能泄漏"：核心编解码路径 `_ENCODER/_DECODER/_RespDECODER/_RespListDECODER` 是模块级单例、msgspec 实现且无锁，是当前已知最快的 msgpack 路径之一；**没有发现 per-message 构造 codec、未释放缓冲区、隐式 GIL 长占等性能泄漏**。唯一可观测的优化空间是热路径上的 `bytes`/struct 分配，属正常开销，非泄漏。真正的高并发性能瓶颈（连接池、session 生命周期、gRPC thread_pool / asyncio 调度）位于**消费方服务**，不在本仓库范围内。

[Types]

本节汇总 msgspec 类型定义层的发现与建议（**不改代码**）。

- **[LOW] T-1　`QueryBody.sid: List[bytes] = []` 使用可变默认值**
  - 位置：`bt_protocol/_protocol.py:15`
  - 证据：`class QueryBody(..., frozen=True): sid: List[bytes] = []`
  - 实测结论（msgspec 0.18.6）：`QueryBody().sid is QueryBody().sid` 为 `False`，且对实例 `.append` 不会影响其它实例。即 **msgspec 已经为每个实例拷贝默认值**，当前**不是**真实的共享状态泄漏。
  - 但该写法 (1) 违反 PEP 8/可变默认反模式，(2) 与其它字段（如 `Event.body: RequestBody = None`）风格不一致，(3) 在未来迁移到普通 `dataclass` 或不同序列化后端时会变成真实陷阱。
  - 建议（未执行）：改为 `sid: List[bytes] = msgspec.field(default_factory=list)`。
  - 影响：代码可维护性 / 防御性。

- **[INFO] T-2　`Event.body: RequestBody = None` 默认值**
  - 位置：`bt_protocol/_protocol.py:55-56`
  - 证据：`RequestBody = Union[QueryBody, RegisterBody, CashBody, OrderBody, None]`，`body: RequestBody = None`
  - 结论：正确，`None` 既是默认值又在 Union 中，round-trip 测试 `test_event_body_defaults_to_none_and_decodes` 通过。无泄漏。

- **[INFO] T-3　全局 codec 单例**
  - 位置：`bt_protocol/_protocol.py:142-145`
  - 证据：`_ENCODER = msgspec.msgpack.Encoder()`、`_DECODER = msgspec.msgpack.Decoder(type=Event)`、`_RespDECODER`、`_RespListDECODER`
  - 结论：msgspec 的 Encoder/Decoder 设计为可复用且线程安全，模块级单例是**推荐用法**，高并发下正确。实测确认存在 `encode_into`（可零拷贝写入预分配 buffer）作为未来优化选项。无泄漏。

- **[LOW] T-4　公开导出私有 codec**
  - 位置：`bt_protocol/__init__.py:23-27`、`tests/test_protocol.py:42-46`
  - 证据：`_ENCODER/_DECODER/_RespDECODER/_RespListDECODER` 以带下划线名字却出现在 `from bt_protocol import ...` 与 `__init__` import 中
  - 结论：API 契约模糊——下划线暗示私有，却对外暴露。维护性风险，非泄漏。
  - 建议（未执行）：提供公开别名（如 `encode_event/decode_event`）或在 `__all__` 显式声明。

- **[MEDIUM] T-5　`OrderBody` 与 ORM `vtOrder` 字段不对齐**
  - 位置：`bt_protocol/_protocol.py:34-42` vs `bt_protocol/schema/trade.py:104-135`
  - 证据：协议 `OrderBody` 有 `sizer_ratio, price, created_dt, filler`，无 `size`；ORM `vtOrder` 有 `size`，且 `vtOrder` 没有任何 `serialize()`。
  - 影响：协议层无法完整表达 ORM 订单状态，回测/交易侧并发写入 `vtOrder` 后无法用统一协议回放。属设计缺口（非运行时泄漏），但会在高并发写入路径上造成"语义泄漏"。
  - 建议（未执行）：明确 `OrderBody` 是"下单请求"语义，而 `vtOrder.serialize()`（如需）应映射到不同的响应 Body；补齐文档与字段。

[Files]

文件级发现与建议（**不改代码**）。

- **[CRITICAL] F-1　`alembic.ini` 硬编码数据库口令（安全泄漏）**
  - 位置：`alembic.ini:89-93`
  - 证据：
    ```ini
    ; sqlalchemy.url = driver://user:pass@localhost/dbname
    ; SECURITY: do not commit real credentials here. ...
    sqlalchemy.url = postgresql+asyncpg://postgres:postgres@localhost:5432/bt_feed
    ```
    注释声称"实际 URL 由 `DATABASE_URL` 注入"，但 `alembic/env.py:34-36` 仅在 `DATABASE_URL` 存在时覆盖；未设置时即回落到这份明文口令，且历史 README 记载过更强口令 `20210718`，说明该字段曾被反复写入真实凭据。
  - 影响：任何拿到仓库的人获得本地/默认 DB 口令；若该口令被复用到其它环境即为生产安全泄漏。
  - 建议（未执行）：将 `sqlalchemy.url` 改为占位符或注释掉，并在 `env.py` 中当 `DATABASE_URL` 缺失时直接 `raise`，强制显式注入；轮换已泄漏口令。

- **[CRITICAL] F-2　gRPC 运行时版本约束与生成代码硬性要求冲突**
  - 位置：`bt_protocol/serialize/pb/bt_protocol_service_pb2_grpc.py:9-26` vs `pyproject.toml:19`
  - 证据：
    - 生成代码：`GRPC_GENERATED_VERSION = '1.83.0'`，并执行 `first_version_is_lower(GRPC_VERSION, '1.83.0')` → `_version_not_supported=True` → `raise RuntimeError(... 'grpcio>=1.83.0' ...)`
    - `pyproject.toml`：`grpcio = "^1.71.0"`（即 `>=1.71,<2.0`）
    - 因此在 `grpcio==1.71.x..1.82.x` 范围内（当前约束允许），**import `bt_protocol_service_pb2_grpc` 立刻抛 `RuntimeError`**。
  - 影响：可用性泄漏——消费方在解析依赖时会装到 1.71~1.82 区间的版本，导致整个 gRPC 数据流接口不可用，且错误发生在 import 期，难以在线上灰度发现。
  - 建议（未执行）：将 `grpcio` 运行时约束提升到 `>=1.83.0,<2.0`（与生成代码一致），或用当前安装的 `grpcio-tools` 重新生成桩代码使两者对齐；同时把 `grpcio-tools` 移出运行时（已正确仅在 build-system）。

- **[MEDIUM] F-3　`pyproject.toml` 配置本地明文 HTTP `devpi` 源**
  - 位置：`pyproject.toml:31-34`
  - 证据：`url = "http://localhost:3141/bt_sdk/dev/+simple/"`，`priority = "supplemental"`
  - 影响：供应链/可用性泄漏——CI 或他人机器不可达；明文 HTTP 易被中间人篡改包。
  - 建议（未执行）：删除该源或迁至 HTTPS 私服，并改为通过环境变量/CI secret 注入。

- **[MEDIUM] F-4　`alembic/env.py` 吞掉 `Exception` 静默禁用 autogenerate**
  - 位置：`alembic/env.py:16-26`
  - 证据：
    ```python
    try:
        from bt_protocol.schema import asset as _asset_models
        from bt_protocol.schema import trade as _trade_models
        target_metadata = MetaData()
        for _mod in (...): ...
    except Exception:
        target_metadata = None
    ```
  - 影响：模型导入失败（例如未来某次 schema 改动触发 ImportError）时，`alembic revision --autogenerate` 静默生成空迁移；并发迭代中极易丢失 schema 变更。
  - 建议（未执行）：缩小 except 范围或改用日志告警 + 显式失败。

- **[LOW] F-5　README 信息过期**
  - 位置：`README.md:11`（版本号 `0.2.1`）、`:22`（声称 msgspec 未声明）、`:148`（`target_metadata = None` 不支持 autogenerate）、`:220`（"没有测试用例"）
  - 证据：实际 `pyproject.toml` 版本 `0.2.5`、已声明 `msgspec = "^0.18.6"`、`env.py` 已设置 `target_metadata`、`tests/test_protocol.py` 已存在 11 个测试。
  - 影响：误导维护者，非运行时泄漏。

- **[LOW] F-6　Avro schema 与 DuckDB 实际产出类型不一致**
  - 位置：`bt_protocol/serialize/avro/ticker.avsc:8-13`（OHLCV 全为 `int`）vs `bt_protocol/template/duckdb_template.py:32-39`（`open, high, low, close` 直接来自 parquet，通常为 float）
  - 影响：若未来启用 Avro 序列化，类型会在 int/float 间截断；当前未生成 Avro 代码，仅文档级风险。

- **[INFO] F-7　`duckdb_template.py` 全部使用参数化查询（`?` 占位）**
  - 位置：`bt_protocol/template/duckdb_template.py:20-24`
  - 结论：无 SQL 注入风险，正确。

[Functions]

函数/方法级发现与建议（**不改代码**）。

- **[MEDIUM] FN-1　`Base.serialize()` / 各 ORM `serialize()` 返回类型与标注不符**
  - 位置：`bt_protocol/schema/trade.py:96,160,195,229`；`bt_protocol/schema/asset.py:23`
  - 证据：`def serialize(self, include_id=False) -> dict:` 但函数体 `return Resp(body=...)`（返回 `Resp`，不是 `dict`）；`asset.Base.serialize` 返回 `dict`，两者命名相同语义不同。
  - 影响：类型契约失真，静态检查失效；消费方在高并发热路径上若按 `dict` 假设去 `json.dumps` 会运行时崩溃。
  - 建议（未执行）：统一返回类型为 `Resp`/`BodyItem` 并修正注解；或重命名为 `to_resp()` 与 `to_dict()` 区分。

- **[LOW] FN-2　`Base.to_dict()` 每次调用都走 `inspect(self).mapper.column_attrs`**
  - 位置：`bt_protocol/schema/trade.py:29-44`
  - 证据：循环内 `inspect(self)`（每行 31），对每个列再做 `isinstance` 分支并把 `Decimal→float`（有损）。
  - 影响：单条记录可忽略；高并发批量序列化（如快照 `SnapshotBody` 含 N 个 `PositionBody`）时反复 introspection 会有可观 CPU 开销，属"性能泄漏"候选但非资源泄漏。
  - 建议（未执行）：把列属性在类层缓存（`__init_subclass__`），并对金额类字段用 `str(Decimal)` 而非 `float` 避免精度泄漏。

- **[INFO] FN-3　`build_ext.py: compile_protos / patch_grpc_imports / build`**
  - 位置：`build_ext.py:12-66`
  - 结论：仅构建期执行（protoc 编译 + 相对导入补丁），不在运行时；`patch_grpc_imports` 用默认编码读写文件，构建环境可控。非运行时泄漏。
  - 附带观察：`patch_grpc_imports` 当前生成结果已是相对导入（见 `_pb2_grpc.py:6` `from . import ...`），补丁幂等。

- **[INFO] FN-4　`alembic/env.py: run_async_migrations` 使用 `pool.NullPool`**
  - 位置：`alembic/env.py:93-102`
  - 结论：迁移场景使用 `NullPool`（连接即用即弃）是**正确**做法，避免迁移期连接泄漏。无问题。

- **[LOW] FN-5　`setup.py:get_ext_modules` 用 `glob.glob("**/*.pyx")`**
  - 位置：`setup.py:13`
  - 证据：仓库当前无 `.pyx`，返回 `[]` 且不调用 `cythonize`（已注释说明，正确）。
  - 结论：构建期行为，无运行时影响。

[Classes]

ORM/结构类级发现与建议（**不改代码**）。

- **[HIGH] C-1　`OrderBit.order_id` 外键目标不唯一（PostgreSQL 将拒绝/引发并发冲突）**
  - 位置：`bt_protocol/schema/trade.py:146`（FK 定义）+ `trade.py:120-124`（`vtOrder` 约束）
  - 证据：
    ```python
    # vtOrder:
    __table_args__ = (UniqueConstraint("order_id", "experiment_id", name="uq_order_id_experiment_id"),)
    # OrderBit:
    order_id: Mapped[bytes] = mapped_column(ForeignKey("vtorder.order_id", ondelete="CASCADE"))
    ```
    `vtorder.order_id` 单列既不是主键也没有单列唯一约束；PostgreSQL 要求 FK 引用列必须具有唯一性或为主键的一部分且该组合整体唯一（此处唯一的是 `(order_id, experiment_id)` 复合，而 `OrderBit` 没有同步包含 `experiment_id` 进 FK）。
  - 影响：DDL 阶段或并发批量 insert `order_bit` 时触发 `there is no unique constraint matching given keys for referenced table "vtorder"`；属**正确性/可用性泄漏**。
  - 建议（未执行）：在 `OrderBit` 增加 `experiment_id` 并使用复合外键 `ForeignKeyConstraint(["order_id","experiment_id"], ...)`，或在 `vtorder.order_id` 上加单列 `UniqueConstraint`。

- **[HIGH] C-2　ORM 关系默认 `lazy="select"`，async 场景高并发必爆（greenlet 泄漏）**
  - 位置：`bt_protocol/schema/trade.py:84-94,126-131,158,191-193,225-227`；`asset.py:48-49`
  - 证据：`relationship(back_populates=...)` 均未指定 `lazy=`，默认 `select`（同步延迟加载）。
  - 影响：消费方若以 `asyncpg + async_session` 使用这些模型，任何在异步上下文外的属性访问会触发同步 IO，抛 `MissingGreenlet` / `IO should be performed from a coroutine`；高并发下表现为大量 greenlet 泄漏与 500。即便同步使用，N+1 查询在批量回放场景下是明显性能泄漏。
  - 建议（未执行）：把所有 `relationship` 显式设为 `lazy="raise"`（禁止隐式延迟加载）或 `lazy="selectin"`，并在服务层用 `selectinload/joinedload` 显式控制；对真正大结果集（如 `order_bits`）考虑分页/流式。

- **[LOW] C-3　`vtAccount` 在独立表上滥用 `use_existing_column=True`**
  - 位置：`bt_protocol/schema/trade.py:213-217`
  - 证据：`portfolio_value/cash/pn/leverage/margin` 均带 `use_existing_column=True`，但 `vtAccount` 并非继承/连接表继承场景。
  - 影响：`use_existing_column` 仅在单表/连接表继承中有意义，在独立表上是语义噪声；不会直接报错，但会误导 autogenerate 与维护者。
  - 建议（未执行）：移除该参数。

- **[LOW] C-4　`User`/`Experiment` 主键设计含隐式自增列与复合 PK 混用**
  - 位置：`bt_protocol/schema/trade.py:51-60,71-82`
  - 证据：`User.id` 自增且与 `user_id/client_id` 共同构成 `PrimaryKeyConstraint("id","user_id","client_id")`；`Experiment` 类似。
  - 影响：自增列作为复合 PK 一员时，PG 行为依赖索引顺序，高并发批量注册时可能产生非预期锁竞争（非泄漏但为性能隐患）。
  - 建议（未执行）：明确以单列 `id` 为 PK，业务唯一用单独 `UniqueConstraint`。

- **[INFO] C-5　msgspec `Struct(frozen=True)` 全员不可变**
  - 位置：`bt_protocol/_protocol.py` 全部结构体
  - 结论：`frozen=True` 保证线程间安全共享，无状态泄漏。正确。

[Dependencies]

依赖矩阵发现与建议（**不改代码**）。

- **[CRITICAL] D-1　`grpcio` 运行时约束 `<1.83`，与生成代码 `>=1.83.0` 冲突**（见 F-2）
  - 建议：`grpcio = ">=1.83.0,<2.0"`，重新生成桩代码锁定一致版本。

- **[MEDIUM] D-2　`devpi` 本地明文 HTTP 源**（见 F-3）

- **[INFO] D-3　`grpcio-tools` 仅在 `[build-system].requires`**
  - 位置：`pyproject.toml:50`
  - 结论：正确——生成代码运行期不需要 `grpcio-tools`，不污染运行时依赖。

- **[INFO] D-4　`msgspec` 已在运行时依赖中正确声明**
  - 位置：`pyproject.toml:24`（`msgspec = "^0.18.6"`），实测版本 `0.18.6`
  - 结论：README 关于"msgspec 未声明"的陈述已过期，当前无依赖泄漏。

- **[LOW] D-5　缺少运行期版本导出**
  - 位置：`bt_protocol/__init__.py`
  - 证据：未暴露 `__version__`，消费方难以在并发集群中校验版本一致性。
  - 建议（未执行）：`from importlib.metadata import version; __version__ = version("bt-protocol")`。

[Testing]

针对本审计结论的测试覆盖建议（**不改代码**）。

现有测试（`tests/test_protocol.py`，11 个用例）覆盖：Avro JSON 合法性、公开 API 可导入、`Event`/`Resp` 各 Body 的 msgspec round-trip。**未覆盖**以下审计关键点：

- **T-补 1（验证 D-1/F-2）**：导入 `bt_protocol.serialize.pb.bt_protocol_service_pb2_grpc` 不抛 `RuntimeError`。当前若在 `grpcio<1.83` 下运行会立刻失败，应作为 CI 门禁。
- **T-补 2（验证 C-1）**：用 `MetaData` + `ForeignKeyConstraint` 静态断言 `OrderBit` 的外键目标列在 `vtorder` 上具备唯一性。
- **T-补 3（验证 C-2）**：遍历 `trade.Base`/`asset.Base` 所有 `relationship`，断言 `lazy in {"raise","selectin","joined","noload"}`（禁止默认 `select`）。
- **T-补 4（验证 F-1）**：静态读取 `alembic.ini`，断言 `sqlalchemy.url` 不含明文口令（仅占位或为空）。
- **T-补 5（性能回归）**：基准 `_ENCODER.encode(Event(...))` 与 `_DECODER.decode(...)` 的吞吐，防止未来引入 per-message codec 分配。
- **T-补 6（类型契约）**：用 `inspect.signature` 断言 `serialize()` 注解与实际返回一致（防 FN-1 回归）。

> 现有 `test_protocol.py` 直接 `from bt_protocol import _ENCODER ...`（私有符号），印证 T-4 的 API 契约模糊。

[Implementation Order]

> 用户已选择"仅做审计报告，不改代码"。以下为**推荐的后续 remediation 优先级**（未执行），供将来作为独立任务排期。

1. **[CRITICAL] 对齐 gRPC 版本**（D-1 / F-2）：升级 `grpcio` 约束到 `>=1.83.0,<2.0` 并重新生成 `_pb2_grpc.py`，新增 T-补 1 作为 CI 门禁——优先级最高，影响所有数据流接口可用性。
2. **[CRITICAL] 清理凭据**（F-1）：从 `alembic.ini` 移除明文口令，`env.py` 在缺失 `DATABASE_URL` 时显式失败；轮换历史泄漏口令。
3. **[HIGH] 修复 `OrderBit` 外键**（C-1）：引入复合外键或单列唯一约束，附 T-补 2。
4. **[HIGH] 关闭 ORM 隐式延迟加载**（C-2）：全量 `lazy="raise"`/`"selectin"`，附 T-补 3——直接决定高并发可用性。
5. **[MEDIUM] `env.py` 异常策略**（F-4）：缩小 except，避免静默禁用 autogenerate。
6. **[MEDIUM] 统一 `serialize()` 契约**（FN-1）：修正返回类型注解，附 T-补 6。
7. **[MEDIUM] 移除本地明文 `devpi` 源**（F-3 / D-2）。
8. **[LOW] 批量整改**：T-1（`default_factory`）、C-3（`use_existing_column`）、T-4（公开 codec API）、D-5（`__version__`）、F-5（刷新 README）、F-6（Avro 类型对齐）。
9. **[INFO/性能] 可选优化**：FN-2 列属性缓存 + 金额精度；热路径评估 `Encoder.encode_into` 零拷贝。

附：高并发"非泄漏"确认清单（无需处理，仅记录）

- 全局 `_ENCODER/_DECODER` 单例：线程安全，正确。
- `msgspec.Struct(frozen=True)`：跨线程安全共享，无状态泄漏。
- DuckDB 模板全参数化：无注入。
- `alembic` 迁移使用 `NullPool`：无连接泄漏。
- msgspec `List[bytes] = []` 默认值：实测每实例独立拷贝，**当前**无共享状态泄漏。
- 运行期无自建线程/进程/连接池/缓存：本仓库不持有任何长生命周期资源，故无传统资源泄漏。