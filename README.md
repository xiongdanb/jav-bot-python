# Jav Telegram Bot

面向 Linux VPS 或服务器常驻运行的 Telegram 番号查询机器人，基于 Python、aiogram 和 SQLite，通过 Telegram 长轮询接收命令，无需部署 Web 服务。发送 `/av SSIS-001` 可查询标题、封面和磁力链接。

## 环境要求

- Python 3.12 或更高版本
- Telegram Bot Token
- 可访问配置的 JavBus 站点

## 服务器部署

### Docker Compose

确保服务器已安装 Docker Engine 和 Docker Compose 插件，然后在项目目录执行：

```bash
cd /opt/jav-bot
mkdir -p data
sudo chown -R 10001:10001 data
cp .env.example .env
chmod 600 .env
```

编辑 `.env` 并填写 `BOT_TOKEN`。之后构建并启动容器：

```bash
docker compose build --pull
docker compose up -d
docker compose ps
docker compose logs -f bot
```

容器使用非 root 用户运行、只读根文件系统，不映射主机端口；Telegram 长轮询和站点查询使用出站网络。SQLite 数据保存在宿主机 `data/`，容器重建不会删除数据库。`.env` 不会复制进镜像。

更新部署：

```bash
git pull
docker compose build
docker compose up -d
```

### Python 直接运行

```bash
cd /opt/jav-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
cp .env.example .env
```

编辑 `.env`，至少设置 `BOT_TOKEN`，然后在服务器运行：

```bash
python -m app.main
```

该命令会以前台进程启动机器人。长期部署时，建议使用 systemd 等服务管理器设置开机启动和异常重启。

## 配置项

| 变量 | 默认值 | 说明 |
|---|---|---|
| `BOT_TOKEN` | 空 | Telegram Bot Token，必填 |
| `JAVBUS_BASE_URL` | `https://www.javbus.com` | 查询站点的 HTTP(S) 根地址 |
| `DATABASE_PATH` | `./data/bot.db` | SQLite 数据库路径 |
| `MAGNET_CACHE_TTL` | `1800` | 磁力信息缓存秒数 |
| `UPSTREAM_ALLOWED_HOSTS` | `www.javbus.com` | 查询站和图片允许访问的主机名，逗号分隔；必须包含站点主机 |
| `GROUP_MAX_MAGNETS` | `3` | 群聊最多显示的磁力链接数 |
| `PRIVATE_MAX_MAGNETS` | `20` | 私聊最多显示的磁力链接数 |
| `MAX_CONCURRENT_FETCHES` | `3` | 同时进行的上游请求上限 |
| `MAX_UPSTREAM_REQUESTS_PER_MINUTE` | `60` | 跨进程共享的上游每分钟请求上限 |
| `MAX_UPSTREAM_RESPONSE_BYTES` | `5242880` | 页面和 AJAX 响应解压后的最大字节数 |
| `USER_COOLDOWN_SECONDS` | `3` | 同一用户在同一聊天的查询间隔 |
| `STATISTICS_TIMEZONE` | `Asia/Shanghai` | 每日统计所用 IANA 时区 |
| `TELEGRAM_SEND_CONCURRENCY` | `2` | 同时发送结果的聊天数上限 |

出于安全考虑，程序仅请求允许列表中的公网主机，并逐跳校验 HTTP 重定向；如果封面使用 CDN，请把 CDN 主机加入 `UPSTREAM_ALLOWED_HOSTS`。程序不会把完整上游 HTML 写入磁盘。

推荐使用锁定依赖：`pip install -r requirements.lock`。更新依赖后应重新生成并提交锁文件。GitHub Actions 会安装锁文件、检查 Python 编译、运行离线单元测试，并验证 Compose 配置和 Docker 镜像构建。

## 命令

- `/start` 或 `/help`：查看使用方法
- `/av SSIS-001`：查询番号，也接受 `ssis001`、`SSIS_001` 和 `SSIS 001`

查询结果默认缓存 30 分钟；群聊与私聊使用不同的链接显示上限。
