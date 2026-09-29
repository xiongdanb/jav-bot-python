# Jav Telegram Bot

一个基于 Python、aiogram 和 SQLite 的 Telegram 番号查询机器人。支持 `/av SSIS-001`，返回标题、封面和磁力链接。

## 环境要求

- Python 3.12 或更高版本
- Telegram Bot Token
- 可访问配置的 JavBus 站点

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
cp .env.example .env       # Windows: Copy-Item .env.example .env
```

编辑 `.env`，至少设置 `BOT_TOKEN`，然后运行：

```bash
python -m app.main
```

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

推荐使用锁定依赖：`pip install -r requirements.lock`。更新依赖后应重新生成并提交锁文件。GitHub Actions 会安装锁文件、检查 Python 编译并运行离线单元测试。

## 命令

- `/start` 或 `/help`：查看使用方法
- `/av SSIS-001`：查询番号，也接受 `ssis001`、`SSIS_001` 和 `SSIS 001`

查询结果默认缓存 30 分钟；群聊与私聊使用不同的链接显示上限。
