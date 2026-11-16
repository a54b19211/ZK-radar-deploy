# ZK-radar-deploy

这台服务器怎么搭起来的，都在这里。业务代码在各自的仓库（fabric、Atlas、BioRadar、BioCheck、MechEvidence、planner），这里只放"公共服务怎么装、怎么起"。

密码和密钥不进仓库：每个目录里需要的 `.env` 由运维放在服务器上（权限 600），仓库里只写要填哪些项。

## 服务器（dev，2026-11-16 起）

- Ubuntu 22.04，32 核，31 GB 内存，系统盘 195 GB，数据盘 `/data` 1 TB。
- 内网 172.16.10.5（旧 zktest 是 172.16.10.3，留给学生）。
- 外网直连很慢，装东西走本机代理 `127.0.0.1:7890`（mihomo）；Docker 的代理配在 `/etc/docker/daemon.json`，Docker 数据在 `/data/docker`。
- 代码放 `/data/projects/<仓库名>`；Python 统一 3.12（uv 0.13.0 装在 `~/.local/bin`，Python 本体在 `/data/python`）。

## 目录

| 目录 | 是什么 |
|---|---|
| `postgres/` | PostgreSQL 17 的参数（`zk.conf`，放 `/etc/postgresql/17/main/conf.d/`） |
| `weknora/` | WeKnora 检索服务和 Neo4j，用官方镜像 |

## PostgreSQL 17

- 装法：官方 apt 源（apt.postgresql.org，jammy-pgdg），包 `postgresql-17`、`postgresql-17-pgvector`。
- 数据目录 `/data/postgresql/17/main`，端口 5432；`pg_hba.conf` 只放行本机和 `172.16.10.0/24`。
- 库：`fabric`（账号 fabric）、`atlas`（账号 atlas），两个库都装了 `vector` 扩展。

## WeKnora

见 `weknora/README.md`。启动：`cd weknora && docker compose --profile neo4j up -d`。

## 启动顺序（待补全）

1. PostgreSQL、Redis（系统服务，开机自启）
2. WeKnora（docker compose）
3. fabric（API、抓取调度、发布）→ fabric 的 WeKnora 桥接
4. Atlas、BioCheck、MechEvidence、planner
5. BioRadar

各服务的 systemd 配置以后统一放到这里的 `systemd/`。监控（Prometheus、Grafana、Loki、告警）以后放 `monitoring/`。
