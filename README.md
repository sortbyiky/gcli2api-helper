# gcli2api-helper

gcli2api 的增强辅助工具，提供自动检验恢复、凭证额度监控、模型统计和实时日志等功能。

## 功能特性

### 🔗 连接配置
- 配置 gcli2api 服务地址和密码
- 连接状态实时显示
- 登录后配置自动锁定

### ⚡ 自动检验恢复
- 定时检测禁用的凭证（可配置间隔，最低 60 秒）
- 自动调用 gcli2api 检验接口恢复凭证
- 支持配置目标错误码（默认 400, 403, 429）
- 手动触发检验功能
- 检验历史记录（查看/下载/清空）

### 📊 凭证额度监控
- 卡片网格展示所有凭证的额度状态
- 支持自动刷新和手动刷新
- 颜色编码直观显示（绿色=正常，黄色=低额度，红色=极低）
- **详细/简洁布局切换**
- **模型过滤器**（多选过滤，选择持久化）
- 多种排序方式（按名称、额度升序/降序、低额度优先）

### 📈 模型统计
- 总调用次数和 Token 消耗统计
- 每个模型的详细调用数据
- Token 格式化显示（K/M 单位）
- 统计数据刷新和重置

### 📋 实时日志
- SSE 实时日志流推送
- 日志分类筛选（全部/gcli2api/检验/警告/错误）
- 自动滚动（可开关）
- 日志下载和清空
- 深色终端主题 + 语法高亮

### 🔐 登录认证
- Session Token 认证
- 登录后自动连接到 gcli2api
- 退出登录功能

### 🔄 版本检查
- 自动检查 GitHub 最新版本
- 发现新版本时提示更新

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

## 界面预览

项目提供 4 个功能 Tab：

| Tab | 功能 |
|-----|------|
| 🔗 连接 | 连接配置 + 自动检验恢复设置 |
| 📈 凭证监控 | 凭证额度卡片/表格展示 |
| 📊 模型统计 | 模型调用次数和 Token 统计 |
| 📋 日志 | 实时日志流 |

## 配置说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| gcli_url | gcli2api 服务地址 | http://127.0.0.1:7861 |
| gcli_password | gcli2api 登录密码 | - |
| auto_verify_enabled | 是否启用自动检验 | false |
| auto_verify_interval | 检查间隔(秒) | 300 |
| auto_verify_error_codes | 触发检验的错误码 | [400, 403, 429] |
| quota_refresh_interval | 额度缓存时间(秒) | 300 |

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/login | POST | 登录获取 Session Token |
| /api/logout | POST | 退出登录 |
| /api/session | GET | 验证 Session Token |
| /api/connect | POST | 连接到 gcli2api |
| /api/config | GET/POST | 获取/保存配置 |
| /api/verify/status | GET | 获取自动检验状态 |
| /api/verify/trigger | POST | 手动触发检验 |
| /api/verify/history | GET | 获取检验历史 |
| /api/verify/history/download | GET | 下载检验历史 |
| /api/verify/history/clear | POST | 清空检验历史 |
| /api/verify/logs/stream | GET | SSE 实时日志流 |
| /api/quota | GET | 获取凭证额度 |
| /api/quota/refresh | POST | 刷新额度缓存 |
| /api/stats | GET | 获取模型统计 |
| /api/stats/reset | POST | 重置统计数据 |
| /api/version | GET | 获取版本信息和检查更新 |

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
