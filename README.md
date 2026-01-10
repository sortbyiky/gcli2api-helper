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

### 方式一：Python 直接运行

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python main.py
```

### 方式二：Docker 运行

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f
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

## 注意事项

- 本工具需要 gcli2api 服务正常运行
- 额度查询仅支持 antigravity 模式的凭证
- 建议检查间隔不低于 60 秒
