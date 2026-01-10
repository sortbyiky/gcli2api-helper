# gcli2api-helper

gcli2api 的辅助工具，提供自动检验恢复和凭证额度监控功能。

## 功能

### 1. 自动检验恢复
- 定时检测禁用的凭证
- 自动调用原项目的检验接口恢复凭证
- 支持配置检查间隔和目标错误码

### 2. 凭证额度监控
- 卡片网格展示所有凭证的额度状态
- 支持自动刷新和手动刷新
- 颜色编码直观显示额度状态

## 快速开始

### 方式一：Docker 拉取镜像（推荐）

```bash
# 拉取最新镜像
docker pull ghcr.io/sortbyiky/gcli2api-helper:latest

# 运行容器
docker run -d \
  --name gcli2api-helper \
  -p 7862:7862 \
  -v ./config.json:/app/config.json \
  --restart unless-stopped \
  ghcr.io/sortbyiky/gcli2api-helper:latest
```

### 方式二：Docker Compose

创建 `docker-compose.yml`：

```yaml
version: '3.8'

services:
  gcli2api-helper:
    image: ghcr.io/sortbyiky/gcli2api-helper:latest
    container_name: gcli2api-helper
    ports:
      - "7862:7862"
    volumes:
      - ./config.json:/app/config.json
    restart: unless-stopped
    environment:
      - TZ=Asia/Shanghai
```

然后运行：

```bash
docker-compose up -d
```

### 方式三：本地构建 Docker

```bash
git clone https://github.com/sortbyiky/gcli2api-helper.git
cd gcli2api-helper
docker-compose up -d --build
```

### 方式四：Python 直接运行

```bash
git clone https://github.com/sortbyiky/gcli2api-helper.git
cd gcli2api-helper
pip install -r requirements.txt
python main.py
```

## 访问

启动后访问 http://127.0.0.1:7862

## 配置说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| gcli_url | gcli2api 服务地址 | http://127.0.0.1:7861 |
| gcli_password | gcli2api 登录密码 | - |
| auto_verify_enabled | 是否启用自动检验 | false |
| auto_verify_interval | 检查间隔(秒) | 300 |
| auto_verify_error_codes | 触发检验的错误码 | [400, 403] |
| quota_refresh_interval | 额度缓存时间(秒) | 300 |

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/connect | POST | 连接到 gcli2api |
| /api/config | GET/POST | 获取/保存配置 |
| /api/verify/status | GET | 获取自动检验状态 |
| /api/verify/trigger | POST | 手动触发检验 |
| /api/verify/history | GET | 获取检验历史 |
| /api/quota | GET | 获取凭证额度 |
| /api/quota/refresh | POST | 刷新额度缓存 |

## 与 gcli2api 配合使用

如果你同时运行 gcli2api 和 gcli2api-helper，可以使用以下 docker-compose.yml：

```yaml
version: '3.8'

services:
  gcli2api:
    image: ghcr.io/su-kaka/gcli2api:latest
    container_name: gcli2api
    ports:
      - "7861:7861"
    volumes:
      - ./credentials:/app/credentials
      - ./config.json:/app/config.json
    restart: unless-stopped

  gcli2api-helper:
    image: ghcr.io/sortbyiky/gcli2api-helper:latest
    container_name: gcli2api-helper
    ports:
      - "7862:7862"
    volumes:
      - ./helper-config.json:/app/config.json
    restart: unless-stopped
    environment:
      - TZ=Asia/Shanghai
    depends_on:
      - gcli2api
```

## 注意事项

- 本工具需要 gcli2api 服务正常运行
- 额度查询仅支持 antigravity 模式的凭证
- 建议检查间隔不低于 60 秒
- Docker 镜像会在每次代码更新时自动构建
