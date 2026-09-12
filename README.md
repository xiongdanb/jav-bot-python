\# Jav Telegram Bot



Telegram 番号查询机器人。



本项目参考并基于 \[nrop19/Find-Jav-bot](https://github.com/nrop19/Find-Jav-bot) 进行 Python 重构，支持本地运行和 Linux VPS 部署。



\---



\## 主要功能



\- `/start` 开始使用

\- `/help` 查看帮助

\- `/av 番号` 查询番号信息

\- 返回番号标题、封面和 Magnet 磁力链接

\- 支持私聊和群聊查询



\---



\## 使用方法



```text

/start

/help

/av SSIS-001

```



\---



\## 环境



\- Ubuntu 22.04 / 24.04

\- Python 3.12+

\- SQLite



\---



\## VPS 部署



\### 1. 安装依赖



```bash

apt update

apt install -y python3 python3-venv python3-pip git

```



\### 2. 拉取项目



```bash

mkdir -p /opt/jav-bot

cd /opt/jav-bot

git clone https://github.com/xiongdanb/jav-bot-python.git .

```



\### 3. 安装 Python 依赖



```bash

python3 -m venv .venv

source .venv/bin/activate

pip install -r requirements.txt

```



\### 4. 配置 `.env`



```env

BOT\_TOKEN=填写你的Telegram机器人Token

ADMIN\_IDS=



JAVBUS\_BASE\_URL=https://www.javbus.com

DATABASE\_PATH=./data/bot.db

CACHE\_TTL=21600

GROUP\_MAX\_MAGNETS=3

PRIVATE\_MAX\_MAGNETS=20

```



\### 5. 启动



```bash

python -m app.main

```



\---



\## 更新



```bash

cd /opt/jav-bot

git pull

```



\---



\## 免责声明



本项目仅供学习与交流，禁止用于任何非法用途。

