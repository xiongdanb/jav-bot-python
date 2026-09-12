<div align="center">

# 🎬 Jav Telegram Bot

<p>基于 Python 的 Telegram 番号查询机器人</p>

<p>
  <a href="https://github.com/xiongdanb/jav-bot-python">
    <img src="https://img.shields.io/github/stars/xiongdanb/jav-bot-python?style=flat-square" alt="Stars">
  </a>
  <a href="https://github.com/xiongdanb/jav-bot-python">
    <img src="https://img.shields.io/github/forks/xiongdanb/jav-bot-python?style=flat-square" alt="Forks">
  </a>
  <img src="https://img.shields.io/badge/Python-3.12+-blue?style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/Platform-Linux-green?style=flat-square" alt="Platform">
</p>

<p>
  <b>支持本地运行 · Linux VPS 部署 · 私聊查询 · 群聊查询</b>
</p>

</div>

---

## 📖 项目简介

本项目参考并基于
[nrop19/Find-Jav-bot](https://github.com/nrop19/Find-Jav-bot)
进行 Python 重构。

用于通过 Telegram Bot 查询番号信息，并获取标题、封面和 Magnet 磁力链接。

---

## ✨ 主要功能

| 功能 | 说明 |
|---|---|
| 🤖 Telegram Bot | 基于 Telegram Bot API |
| 🔍 番号查询 | 支持多种番号格式 |
| 🖼️ 封面信息 | 返回番号标题和封面 |
| 🧲 Magnet | 获取 Magnet 磁力链接 |
| 👤 私聊查询 | 支持私聊使用 |
| 👥 群聊查询 | 支持群组使用 |
| 💾 数据存储 | SQLite 保存相关数据 |

---

## 🚀 使用方法

在 Telegram 中发送：

```text
/start
/help
/av SSIS-001
```

例如：

```text
/av SSIS-001
```

---

## 🖥️ 环境要求

- Ubuntu 22.04 / 24.04
- Python 3.12+
- SQLite

---

## 📦 VPS 部署

### 1. 安装依赖

```bash
apt update
apt install -y python3 python3-venv python3-pip git
```

### 2. 拉取项目

```bash
mkdir -p /opt/jav-bot
cd /opt/jav-bot
git clone https://github.com/xiongdanb/jav-bot-python.git .
```

### 3. 安装 Python 依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. 配置 `.env`

```env
BOT_TOKEN=填写你的Telegram机器人Token
JAVBUS_BASE_URL=https://www.javbus.com
DATABASE_PATH=./data/bot.db
CACHE_TTL=21600
GROUP_MAX_MAGNETS=3
PRIVATE_MAX_MAGNETS=20
```

### 5. 启动

```bash
python -m app.main
```

---

## 🔄 更新项目

```bash
cd /opt/jav-bot
git pull
```

---

## ⚠️ 免责声明

本项目仅供学习与技术交流，禁止用于任何非法用途。

<div align="center">

**Made with Python 🐍**

</div>