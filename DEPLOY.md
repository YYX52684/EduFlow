# EduFlow 服务器部署指南

将 Web 服务部署到一台服务器后，所有人通过同一网址访问，每人有独立工作区，数据互不影响。

---

## 一、服务器要求

- **系统**：Linux（如 Ubuntu 20.04+、CentOS 7+）
- **Python**：**3.8 及以上，推荐 3.10 或 3.11**（若不用 Docker）。`openai>=1.0.0` 需要 Python 3.8+，否则 pip 只能看到 0.10.x 导致安装失败。
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

**生产环境安全（启用登录后必做）**：在 `.env` 中设置：
- `EDUFLOW_ENV=production`（设为生产模式）
- `JWT_SECRET=<随机长字符串>`（如 `openssl rand -hex 32` 生成）

未设置或使用默认 JWT 密钥时，服务将**拒绝启动**，避免 token 被伪造。

### 4. 前台试运行

```bash
source venv/bin/activate
python run_web.py
```

浏览器访问 `http://服务器IP:8000`，确认正常后 Ctrl+C 停止。

### 5. 用 systemd 保活（开机自启、崩溃重启）

生产环境建议用 uvicorn 直接跑且**关闭 reload**（`run_web.py` 带 reload 适合本机开发）。创建服务文件：

```bash
sudo nano /etc/systemd/system/eduflow.service
```

写入（路径按你实际修改；若项目不在 `/opt/EduFlow` 请替换为实际路径）：

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
ExecStart=/opt/EduFlow/venv/bin/uvicorn api.app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

- 若用当前用户跑而不是 `www-data`，可改为 `User=你的用户名`，并保证该用户对项目目录有读权限、对 `workspaces` 有读写权限。
- 若不用虚拟环境：`ExecStart=/usr/bin/python3 -m uvicorn api.app:app --host 0.0.0.0 --port 8000`，且需在项目目录下执行。

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

**前提**：域名已解析到本机公网 IP（在域名服务商处添加 A 记录，如 `eduflow.你的域名.com` → 你的 ECS IP）。

- **CentOS / 阿里云**（用 conf.d）：
  ```bash
  sudo nano /etc/nginx/conf.d/eduflow.conf
  ```
- **Ubuntu / Debian**（用 sites-available）：
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

- **CentOS**：保存后直接 `sudo nginx -t && sudo systemctl reload nginx`（conf.d 会自动加载）。
- **Ubuntu**：`sudo ln -sf /etc/nginx/sites-available/eduflow /etc/nginx/sites-enabled/`，再 `sudo nginx -t && sudo systemctl reload nginx`。

### 3. 放行 80/443（防火墙 + 阿里云安全组）

- **本机 firewalld**：`sudo firewall-cmd --permanent --add-service=http --add-service=https && sudo firewall-cmd --reload`
- **阿里云**：安全组入方向添加 80/tcp、443/tcp，授权对象 0.0.0.0/0。

### 4. 申请免费 HTTPS 证书

**Ubuntu**：`sudo apt install certbot python3-certbot-nginx -y`  
**CentOS 7/8**：先装 EPEL，再装 certbot（或使用 snap）：
```bash
sudo yum install -y epel-release
sudo yum install -y certbot python3-certbot-nginx
# 若没有 python3-certbot-nginx，可：sudo certbot --nginx -d 域名 会提示安装依赖
```

然后执行（替换为你的域名）：

```bash
sudo certbot --nginx -d eduflow.你的域名.com
```

按提示输入邮箱、同意条款；可选「是否将 HTTP 重定向到 HTTPS」选 2（推荐）。完成后访问：`https://eduflow.你的域名.com`。

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

---

## 七、交接 / 离职留用清单

部署到服务器后，你人不在也能让同事继续用。建议把下面信息交给接手人（负责人或运维）。

### 1. 访问方式

- **访问地址**：`https://你的域名` 或 `http://服务器IP:8000`（若未配 Nginx）
- **使用说明**：把 [docs/开放给同事使用.md](docs/开放给同事使用.md) 里「给同事的使用说明」部分发给大家，或贴到内部文档：每人收藏自己的工作区链接（首次打开会得到 `/w/xxx`），平台配置在页内填自己的智慧树信息即可。

### 2. API Key（重要）

- 生成卡片依赖 `.env` 里的 `DEEPSEEK_API_KEY`。
- **建议**：用公司/团队共用的 DeepSeek 账号申请 API Key，或让负责人自己申请后填进服务器上的 `.env`，避免用你个人密钥，离职后失效。
- 位置：服务器上项目目录下的 `.env` 文件（不要提交到 Git）。

### 3. 重要路径与备份

| 内容       | 路径（示例） |
|------------|----------------|
| 环境配置   | `/opt/EduFlow/.env` |
| 所有用户工作区数据 | `/opt/EduFlow/workspaces/` |
| 项目代码   | `/opt/EduFlow`（可从 Git 拉取） |

建议定期备份 `workspaces` 目录（剧本、生成的卡片、各人平台配置都在里面）。

### 4. 日常维护命令（给运维/接手人）

```bash
# 查看服务状态
sudo systemctl status eduflow

# 重启服务（改完 .env 或拉代码后）
sudo systemctl restart eduflow

# 看实时日志
journalctl -u eduflow -f

# 若用 Docker
docker logs -f eduflow
docker restart eduflow
```

**代码更新（你刚推到 GitHub 后，在服务器上这样更新网站）：**

1. SSH 登录阿里云 ECS：`ssh root@你的公网IP`（或你的用户名）。
2. 进入项目目录：`cd /opt/EduFlow`（若你当时克隆到了别的路径，改成那个路径）。
3. 拉取最新代码：`git pull origin main`（若主分支叫 `master` 则用 `git pull origin master`）。
4. 若有新依赖：先激活虚拟环境 `source venv/bin/activate`，再执行 `pip install -r requirements.txt`。
5. 重启服务使新代码生效：
   - **用 systemd 时**：`sudo systemctl restart eduflow`
   - **用 Docker 时**：`docker restart eduflow`
6. 检查状态：`sudo systemctl status eduflow` 或 `docker ps`，再在浏览器访问你的网站确认。

以后每次在本地改完并 `git push` 到 GitHub，在服务器上重复步骤 2～5 即可更新网站内容。

### 5. 可选：文档与仓库

- 部署步骤：本文 [DEPLOY.md](DEPLOY.md)
- 使用与开放方式：[docs/开放给同事使用.md](docs/开放给同事使用.md)
- 把 Git 仓库权限交给团队或公司账号，方便后续改代码、排错。

---

## 八、阿里云 ECS 部署说明

你已有阿里云 ECS 时，按下面顺序做即可，应用部署本身仍按上文「二、直接运行」或「三、Docker」执行。

### 1. 安全组（必须）

ECS 通过**安全组**控制入站流量，不开放端口外网无法访问。

- 登录 [阿里云控制台](https://ecs.console.aliyun.com) → 找到你的 ECS 实例 → 点击实例 ID → **安全组** → **配置规则** → **入方向** → **手动添加**。
- 建议放行：

| 端口 | 用途 |
|------|------|
| 22 | SSH 登录（必开） |
| 80 | HTTP（用 Nginx 时） |
| 443 | HTTPS（用 Nginx + 证书时） |
| 8000 | 若**不用** Nginx，直接访问 `http://公网IP:8000` 时必开 |

保存后即可生效。

### 2. SSH 登录 ECS

- **公网 IP**：在 ECS 实例详情页可以看到「公网 IP」。
- Windows：用 PowerShell / CMD 或 [PuTTY](https://www.putty.org/)，执行 `ssh root@你的公网IP`（或你创建的用户名）。
- 首次会提示确认指纹，输入 yes；密码或密钥按你购买/创建实例时设置的来。

若用密钥登录，示例：

```bash
ssh -i "你的密钥.pem" root@你的公网IP
```

### 3. 系统与目录建议

- 镜像推荐 **Ubuntu 22.04 LTS**（若你选的是 CentOS 也可以，命令略有不同，本文以 Ubuntu 为例）。
- 项目可放在 `/opt/EduFlow` 或 `~/EduFlow`，后文以 `/opt/EduFlow` 为例；若你放别处，把 DEPLOY 里所有该路径改成你的路径即可。

### 4. 在 ECS 上部署应用

登录 ECS 后，按 **[二、方式一：直接运行](#二方式一直接运行推荐先试)** 或 **[三、方式二：Docker 部署](#三方式二docker-部署)** 操作即可：

1. 安装 Python 3.10+（Ubuntu：`sudo apt update && sudo apt install -y python3 python3-venv python3-pip git`）或 Docker。
2. `cd /opt`，`git clone <你的仓库地址> EduFlow`，`cd EduFlow`。
3. 配置 `.env`（至少 `DEEPSEEK_API_KEY`）。
4. 试运行：`python run_web.py` 或 Docker 方式，用浏览器访问 `http://你的公网IP:8000` 验证。
5. 配置 systemd 或 Docker 常驻、开机自启（见第二节第 5 步或第三节）。

**注意**：若安全组没开 8000，这里会访问不到，先到控制台把 8000 入方向放开再试。

### 5. 可选：绑定域名与 HTTPS

- 若有域名（不限是否在阿里云买）：在阿里云 **云解析 DNS** 里添加一条 **A 记录**，主机记录填子域名（如 `eduflow`），记录值填 ECS 的**公网 IP**，这样 `eduflow.你的域名.com` 就会解析到你这台 ECS。
- 在 ECS 上按 **[四、Nginx 反代 + HTTPS](#四可选nginx-反代--https推荐生产环境)** 配置 Nginx 和 certbot，即可用 `https://eduflow.你的域名.com` 访问。
- 用域名后，安全组只需放行 22、80、443，可**不再**对公网开放 8000，更安全。

### 6. 简要自检

- 能 SSH 登录、能 `curl http://127.0.0.1:8000` 或浏览器访问 `http://公网IP:8000` 并跳转到 `/w/xxx` 即表示服务正常。
- 若用 Nginx，访问 `https://你的域名` 同样应跳转到工作区。

后续交接、备份、维护按 **[七、交接/离职留用清单](#七交接--离职留用清单)** 交给同事即可。

### 常见问题：pip 报错 No matching distribution found for openai>=1.0.0

说明当前 **Python 版本过旧**（如 3.6/3.7），需要安装 Python 3.10 并用新版本创建 venv。

**先看版本：** `python3 --version`

**Ubuntu 20.04/22.04：**

```bash
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3.10-dev
cd /opt/EduFlow
rm -rf venv
python3.10 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**CentOS 7 / 阿里云 CentOS 镜像：**

```bash
sudo yum install -y gcc openssl-devel bzip2-devel libffi-devel zlib-devel
cd /usr/src
sudo curl -O https://www.python.org/ftp/python/3.10.13/Python-3.10.13.tgz
sudo tar xzf Python-3.10.13.tgz
cd Python-3.10.13
sudo ./configure --enable-optimizations
sudo make altinstall
cd /opt/EduFlow
rm -rf venv
python3.10 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**若已安装 Python 3.10 但不在 PATH：** 用 `python3.10 -m venv venv` 创建虚拟环境即可。systemd 里 `ExecStart` 和 `Environment` 中的 Python 路径要对应到该 venv（如 `/opt/EduFlow/venv/bin/uvicorn`）。
