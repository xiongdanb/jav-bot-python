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
| `CACHE_TTL` | `21600` | 查询缓存秒数 |
| `GROUP_MAX_MAGNETS` | `3` | 群聊最多显示的磁力链接数 |
| `PRIVATE_MAX_MAGNETS` | `20` | 私聊最多显示的磁力链接数 |
| `MAX_CONCURRENT_FETCHES` | `3` | 同时进行的上游请求上限 |
| `USER_COOLDOWN_SECONDS` | `3` | 同一用户在同一聊天的查询间隔 |
| `DEBUG_SAVE_HTML` | `false` | 是否保存上游 HTML 以排查解析问题 |
| `DEBUG_DIR` | `./debug` | 调试 HTML 保存目录 |
| `STATISTICS_TIMEZONE` | `Asia/Shanghai` | 每日统计所用 IANA 时区 |

调试 HTML 可能包含上游页面内容，默认关闭；启用后应妥善保护和定期清理该目录。

## 命令

- `/start` 或 `/help`：查看使用方法
- `/av SSIS-001`：查询番号，也接受 `ssis001`、`SSIS_001` 和 `SSIS 001`

查询结果缓存于 SQLite，默认缓存 6 小时。群聊与私聊使用不同的链接显示上限。
