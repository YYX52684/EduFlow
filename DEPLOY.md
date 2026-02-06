# EduFlow 服务器部署指南

将 Web 服务部署到一台服务器后，所有人通过同一网址访问，每人有独立工作区，数据互不影响。

---

## 一、服务器要求

- **系统**：Linux（如 Ubuntu 20.04+、CentOS 7+）
- **Python**：3.10 或 3.11（若不用 Docker）
- **端口**：8000 可用，或通过 Nginx 反代 80/443

---

## 二、方式一：直接运行（推荐先试）

### 1. 在服务器上克隆项目

```bash
cd /opt   # 或你希望的目录
git clone <你的仓库地址> EduFlow
cd EduFlow
```

### 2. 安装依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
nano .env   # 或 vim，至少填写 DEEPSEEK_API_KEY
```

必填：`DEEPSEEK_API_KEY`。注入功能需填写智慧树相关配置。

### 4. 前台试运行

```bash
source venv/bin/activate
python run_web.py
```

浏览器访问 `http://服务器IP:8000`，确认正常后 Ctrl+C 停止。

### 5. 用 systemd 保活（开机自启、崩溃重启）

创建服务文件：

```bash
sudo nano /etc/systemd/system/eduflow.service
```

写入（路径按你实际修改）：

```ini
[Unit]
Description=EduFlow Web Service
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/EduFlow
Environment="PATH=/opt/EduFlow/venv/bin"
ExecStart=/opt/EduFlow/venv/bin/python run_web.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

若不用虚拟环境，可改为：

```ini
ExecStart=/usr/bin/python3 run_web.py
```

启用并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable eduflow
sudo systemctl start eduflow
sudo systemctl status eduflow
```

日志：`journalctl -u eduflow -f`

---

## 三、方式二：Docker 部署

### 1. 在服务器上克隆项目并准备 .env

```bash
cd /opt
git clone <你的仓库地址> EduFlow
cd EduFlow
cp .env.example .env
nano .env   # 填写 DEEPSEEK_API_KEY 等
```

### 2. 构建并运行

```bash
docker build -t eduflow .
docker run -d \
  --name eduflow \
  -p 8000:8000 \
  --env-file .env \
  -v /opt/EduFlow/workspaces:/app/workspaces \
  --restart unless-stopped \
  eduflow
```

- `-v ... workspaces`：工作区数据持久化到宿主机。
- 访问：`http://服务器IP:8000`。

### 3. 常用命令

```bash
docker logs -f eduflow    # 看日志
docker restart eduflow    # 重启
docker stop eduflow && docker rm eduflow   # 停止并删除容器，需时再 run
```

---

## 四、可选：Nginx 反代 + HTTPS（推荐生产环境）

让用户通过 `https://eduflow.你的域名.com` 访问，并解决「选择目录」需要 HTTPS 的问题。

### 1. 安装 Nginx 与 certbot

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install nginx certbot python3-certbot-nginx -y
```

### 2. 配置 Nginx

```bash
sudo nano /etc/nginx/sites-available/eduflow
```

写入（替换为你的域名）：

```nginx
server {
    listen 80;
    server_name eduflow.你的域名.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

启用并重载：

```bash
sudo ln -s /etc/nginx/sites-available/eduflow /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 3. 申请免费 HTTPS 证书

```bash
sudo certbot --nginx -d eduflow.你的域名.com
```

按提示选择是否重定向 HTTP 到 HTTPS。之后访问：`https://eduflow.你的域名.com`。

---

## 五、防火墙

若直接暴露 8000 端口：

```bash
# Ubuntu (ufw)
sudo ufw allow 8000
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

若用 Nginx 反代，只开 80/443 即可，不必开 8000 对外。

---

## 六、简要检查清单

| 项           | 说明 |
|-------------|------|
| 服务可访问   | 浏览器打开 `http://服务器IP:8000` 或你的域名，会跳转到 `/w/xxx` |
| 工作区隔离   | 不同浏览器/无痕窗口会得到不同 `/w/xxx`，数据独立 |
| 生成卡片     | 需保证 `.env` 中 `DEEPSEEK_API_KEY` 正确 |
| 注入平台     | 各人在页内「平台配置」填写自己的智慧树信息并保存 |

更多使用说明见 [README.md](README.md) 第四节 Web 交互。
