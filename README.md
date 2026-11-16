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
| `systemd/` | 各服务的 systemd 用户单元（见下文） |

## PostgreSQL 17

- 装法：官方 apt 源（apt.postgresql.org，jammy-pgdg），包 `postgresql-17`、`postgresql-17-pgvector`。
- 数据目录 `/data/postgresql/17/main`，端口 5432；`pg_hba.conf` 只放行本机和 `172.16.10.0/24`。
- 库：`fabric`（账号 fabric）、`atlas`（账号 atlas），两个库都装了 `vector` 扩展。

## WeKnora

见 `weknora/README.md`。启动：`cd weknora && docker compose --profile neo4j up -d`。

## 启动顺序

1. PostgreSQL 17、Redis（系统服务，开机自启）
2. WeKnora（docker compose，`--profile neo4j`）
3. fabric：`datafabric-api` → `datafabric-weknora`（桥接）→ `datafabric-fetch-worker`、`datafabric-scheduler`、`datafabric-clean`、`datafabric-index`
4. Atlas（`atlas-api`、`atlas-pull`）、`bioradar-biocheck`、`bioradar-mechevidence`、`bioradar-planner`
5. BioRadar：`bioradar-api`、`bioradar-worker`、`bioradar-monitor`

## systemd（用户单元，账号 zk_admin）

`systemd/` 里是全部单元。装法：

```bash
loginctl enable-linger zk_admin                     # 不登录也常驻（已开）
cp systemd/*.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now <单元名>               # 按上面的顺序
journalctl --user -u <单元名> -f                     # 看日志
```

| 单元 | 端口（127.0.0.1） | 配置文件（权限 600） |
|---|---|---|
| datafabric-api | 18511 | `~/.config/datafabric-publication/runtime.env` |
| datafabric-scheduler、fetch-worker、clean、index | — | 同上 |
| datafabric-weknora（桥接） | 18564 | `~/.config/weknora-kdd/runtime.json` |
| atlas-api | 8100 | `~/.config/atlas/atlas.env` |
| atlas-pull | — | 同上 |
| bioradar-planner | 18561 | `~/.config/bioradar/planner.env` |
| bioradar-biocheck | 18562 | `~/.config/bioradar/biocheck.env` |
| bioradar-mechevidence | 18563 | `~/.config/bioradar/mechevidence.env` |
| bioradar-api | 18100 | `~/.config/bioradar/radar.env` |
| bioradar-worker、monitor | — | 同上 |

几条约定：

- 服务之间的令牌一处生成、两边一致：fabric 读令牌（fabric → Atlas、BioRadar）、桥接令牌（`WEKNORA_KDD_TOKEN` = runtime.json 的 `token`）、planner / BioCheck / MechEvidence 各自的 `SERVICE_TOKEN`（= radar.env 里对应的 `*_TOKEN`）。
- WeKnora 里的账号、API Key、知识库、模型编号记在 `~/.config/weknora-kdd/weknora-setup.json`。
- fabric 抓取走本机代理（runtime.env 的 `HTTPS_PROXY`），本机、内网模型和 DeepSeek 在 `NO_PROXY` 里直连。
- BioRadar 用本机 PostgreSQL 的 `bioradar` 库（账号 bioradar）和系统 Redis 的 5 号库；建表：`PYTHONPATH=services .venv/bin/alembic -c db/alembic.ini upgrade head`。
- fabric 附件解析（`python -m run.attachments --loop`）和雷达前端目前没有单元，没起。
