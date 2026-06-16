# python -m grpc_tools.protoc -I . --python_out=. --pyi_out=. --grpc_python_out=. service.proto 

#### 1. 修正 `bt-protocol/pyproject.toml` (最关键)

`grpcio-tools` 是一个 **编译器（Compiler）**。它的作用是把 `.proto` 变成 `.py`。一旦编译完成，代码运行只需要 `grpcio` 和 `protobuf` 库，**不需要** `grpcio-tools`。

你误把编译器放进了 `dependencies`（运行时依赖），导致每个安装 `bt-protocol` 的项目都被迫去安装这个编译器，从而引发版本锁死。

**请修改 `bt-protocol/pyproject.toml`：**


main ---> dev

git checkout dev / git fetch origin / git merge origin/main / git add .  and commit and solve conflicts / git push origin dev

rebase

git checkout dev / git fetch origin / git rebase origin main / git add . and git rebase --continue not need commit / git push origin dev --force-with-lease

# blob to transform string to bytes
# alembic init alembic --template gener / async 
# alembic revision -m "change sid and name from str to bytes"
# alembic upgrade head / trade@head
# alembic heads
# alembic revision --head 30aae0684ec1 -m "revise unqiue order_id in order_bit"
# alembic downgrade/upgrade *****

# postgres export

# -s 代表 --schema-only (只导出结构)
pg_dump -U postgres -d table -t users --schema-only mydb > schema.sql
pg_dump -U postgres -d my_db -s -f only_schema.sql

# -a 代表 --data-only (只导出数据)
pg_dump -U postgres -d table -t users --data-only mydb > data.sql # --format=custom
pg_dump -U postgres -d my_db -a -f data.sql

# -t 代表 --table
pg_dump -U postgres -d my_db -t adjustment -f adj_table.sql

# load
psql -h 192.168.x.x -p 5432 -U postgres -d my_db -f data.sql

# postgres first time
sudo -i -u postgres / psql -U postgres # postgres is admin

ALTER USER postgres WITH PASSWORD '****';

CREATE USER myuser WITH PASSWORD '****';

CREATE DATABASE mydb OWNER myuser;

GRANT ALL PRIVILEGES ON DATABASE mydb TO myuser;

PostgreSQL 默认采用 peer 或 ident 认证（即只信任操作系统同名用户）, 通过工具用用户名+密码的方式登录，必须修改pg_hba.conf 配置文件

/etc/postgresql/版本号/main/ 或 /var/lib/pgsql/data/ 

sudo nano /etc/postgresql/15/main/pg_hba.conf

# TYPE  DATABASE        USER            ADDRESS                 METHOD

# 本地通过 Unix 套接字连接（将 peer 改为 scram-sha-256）
local   all             all                                     scram-sha-256

# 本地 IPv4 连接（将 ident 改为 scram-sha-256）
host    all             all             127.0.0.1/32            scram-sha-256

需要允许远程工具连接：

host  all  all  0.0.0.0/0  scram-sha-256

打开同目录下的 postgresql.conf #listen_addresses = 'localhost' 改为 listen_addresses = '*'

# Ubuntu / Debian
sudo systemctl restart postgresql

# CentOS / RHEL
sudo systemctl restart postgresql-15

# macOS (Homebrew)
brew services restart postgresql

# for test
psql -U myuser -d mydb -h 127.0.0.1 -W

DROP TABLE IF EXISTS adjustment CASCADE;

在 SQLAlchemy default 和 server_default 有本质区别
default=0 (Python 侧) 当你用 ORM 创建新对象且没给 delist 赋值时，SQLAlchemy 会在发送 INSERT 语句前，自动在 Python 里把这个字段填上 0, 数据库感知不到任何“默认值”的存在
server_default="0" (数据库侧) SQLAlchemy 会在 CREATE TABLE 时加上 DEFAULT 0。当你 INSERT 忽略该列时，由 PostgreSQL 亲自把 0 填进去
