## 资源监控路径统一配置（pan115 与 CloudDrive2）

为避免路径心智混乱，系统统一采用“相对在线路径”填写方式：

- 在 CloudDrive2 设置页，填写“默认根路径（在线路径）”，例如 `/115open` 或 `/115open2`。
- 在资源监控规则里，填写相对路径（不包含根名），如 `分类/电影/{YYYY}/{MM}`。
- 系统会自动映射：
  - 115 转存：`/` + 相对路径 → 自动创建/获取目录ID后转存。
  - CloudDrive2 离线：`<在线根>` + `/` + 相对路径 → 不存在则逐级创建目录（不支持 CreateFolder 时提示手工创建）。

可选：按类型使用不同目录（覆盖默认`target_path`）：
- `target_path_pan115`：115分享链接目录
- `target_path_magnet`：磁力离线目录
- `target_path_ed2k`：ed2k离线目录

支持变量：`{YYYY}/{MM}/{DD}/{chat}/{rule}`。前端会展示双预览（pan115 与 CloudDrive2）。

注意：禁止填写 `/CloudNAS/...`。如填写了以 `/115open/...` 开头的绝对路径，会自动剥离为相对层级用于统一映射。

# TMC 配置指南

## 📋 配置方式概述

TMC 支持两种配置方式，可以灵活选择或混合使用：

### 🎯 方式 A：网页端配置（推荐）⭐

**适用场景：**
- 多客户端管理
- 不同客户端使用不同的 API 凭证
- 无需重启容器即可添加/修改客户端

**使用步骤：**
1. 启动 TMC 服务（无需配置环境变量）
2. 登录网页管理界面
3. 进入"客户端管理"页面
4. 点击"添加客户端"，填写客户端专属配置：
   - **用户客户端**：`API_ID`、`API_HASH`、`PHONE_NUMBER`
   - **机器人客户端**：`BOT_TOKEN`、`ADMIN_USER_ID`

**优点：**
- ✅ 灵活：每个客户端可以使用不同的 API 凭证
- ✅ 动态：无需重启容器
- ✅ 安全：配置存储在数据库中，支持备份
- ✅ 便捷：通过网页界面操作，无需编辑配置文件

---

### 🔧 方式 B：环境变量配置（全局配置）

**适用场景：**
- 单客户端场景
- 所有客户端共享同一套 API 凭证
- 使用已有的环境变量管理系统

**配置步骤：**

1. **编辑 `docker-compose.yml`**
   ```yaml
   environment:
     - API_ID=1234567
     - API_HASH=abcdef1234567890
     - BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
     - PHONE_NUMBER=+8613800138000
     - ADMIN_USER_IDS=123456789,987654321
   ```

2. **或者创建 `.env` 文件**
   ```bash
   API_ID=1234567
   API_HASH=abcdef1234567890
   BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
   PHONE_NUMBER=+8613800138000
   ADMIN_USER_IDS=123456789,987654321
   ```

3. **重启服务**
   ```bash
   docker compose down
   docker compose up -d
   ```

**优点：**
- ✅ 传统：适合熟悉环境变量配置的用户
- ✅ 集中：所有配置在一个文件中
- ✅ 自动化：便于脚本化部署

---

## 🔄 配置优先级

当同时存在多种配置时，优先级如下：

```
客户端配置（网页端） > 全局配置（环境变量）
```

**示例场景：**

1. **全局 fallback + 客户端覆盖（推荐）** ⭐
   - 环境变量设置默认的 `API_ID` 和 `API_HASH`
   - 网页端添加客户端时，可以覆盖这些默认值
   - 适合大多数场景，兼顾灵活性和便捷性

2. **纯网页端配置**
   - 不设置任何环境变量（或留空）
   - 所有配置通过网页端添加
   - 最灵活，但需要为每个客户端单独配置

3. **纯环境变量配置**
   - 设置全局环境变量
   - 不通过网页端添加客户端配置
   - 所有客户端共享同一套凭证

---

## 📝 配置项说明

### Telegram API 配置

| 配置项 | 说明 | 获取方式 | 必填 |
|--------|------|----------|------|
| `API_ID` | Telegram API ID | https://my.telegram.org | 客户端配置或全局配置二选一 |
| `API_HASH` | Telegram API Hash | https://my.telegram.org | 客户端配置或全局配置二选一 |
| `BOT_TOKEN` | Bot Token | @BotFather | 机器人客户端必填 |
| `PHONE_NUMBER` | 手机号（国际格式） | - | 用户客户端必填 |
| `ADMIN_USER_IDS` | 管理员用户ID（逗号分隔） | - | 可选 |

**重要说明：**
- **用户客户端**：必须提供 `API_ID` + `API_HASH` + `PHONE_NUMBER`（可以在网页端或环境变量中配置）
- **机器人客户端**：必须提供 `BOT_TOKEN` + `ADMIN_USER_ID`，`API_ID` 和 `API_HASH` 可选（留空则使用全局配置）
  - 推荐：为每个 Bot 使用不同的 API 凭证，避免速率限制
  - 简化：多个 Bot 共享全局的 `API_ID` 和 `API_HASH`（在环境变量中配置）

### 应用配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `APP_PORT` | 应用端口 | `9393` |
| `TZ` | 时区 | `Asia/Shanghai` |
| `JWT_SECRET_KEY` | JWT 密钥 | `your-super-secret-jwt-key-change-me` |
| `DATABASE_URL` | 数据库地址 | `sqlite:///data/bot.db` |
| `LOG_LEVEL` | 日志级别 | `INFO` |

Web 登录保护：同一 IP 在 15 分钟内连续登录失败 5 次（包括用户名不存在、密码错误或账号停用），封禁登录 15 分钟。登录成功清除失败记录；封禁期间即使密码正确也返回 HTTP 429，响应头 `Retry-After` 表示剩余等待秒数。记录保存在当前进程内存中，服务重启后清空，适用于默认单进程部署。

反向代理部署时，通过 Uvicorn 的 `FORWARDED_ALLOW_IPS` 环境变量指定可信代理的实际连接 IP（默认仅信任 `127.0.0.1`），并由代理正确设置 `X-Forwarded-For`。否则所有用户可能按代理 IP 共同计数；不要在后端可被直接访问时设置为 `*`。

### 代理配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `ENABLE_PROXY` | 启用代理 | `false` |
| `PROXY_TYPE` | 代理类型（http/socks4/socks5） | `http` |
| `PROXY_HOST` | 代理服务器地址 | `127.0.0.1` |
| `PROXY_PORT` | 代理端口 | `7890` |
| `HTTP_PROXY` | HTTP 代理（标准环境变量） | - |
| `HTTPS_PROXY` | HTTPS 代理（标准环境变量） | - |

### Docker 权限配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `PUID` | 用户ID | `1000` |
| `PGID` | 组ID | `1000` |

---

## 🚀 快速开始示例

### 示例 1：纯网页端配置（推荐新手）

```bash
# 1. 启动服务（无需配置）
docker compose up -d

# 2. 访问 http://localhost:9393
# 3. 登录后进入"客户端管理"
# 4. 添加客户端，填写 API_ID、API_HASH 等信息
```

### 示例 2：混合配置（推荐进阶用户）

```bash
# 1. 创建 .env 文件，设置默认值
cat > .env << EOF
API_ID=1234567
API_HASH=abcdef1234567890
PHONE_NUMBER=+8613800138000
EOF

# 2. 启动服务
docker compose up -d

# 3. 网页端可以覆盖这些默认值
#    例如：添加客户端时使用不同的 API_ID
```

### 示例 3：环境变量配置（推荐自动化部署）

```bash
# 1. 编辑 docker-compose.yml
# 2. 设置所有必要的环境变量
# 3. 启动服务
docker compose up -d
```

---

## ❓ 常见问题

### Q1: 我已经在 docker-compose.yml 中配置了 API_ID，为什么还要在网页端填写？

**A:** 不需要！配置优先级是：网页端 > 环境变量。如果你在 docker-compose.yml 中配置了全局的 `API_ID` 和 `API_HASH`：
- **用户客户端**：网页端可以留空这两项，系统会自动使用全局配置
- **机器人客户端**：网页端的 `API_ID` 和 `API_HASH` 字段本身就是可选的

但如果你想为某个客户端使用不同的 API 凭证，可以在网页端覆盖。

---

### Q2: 我可以完全不配置环境变量吗？

**A:** 可以！直接启动服务，然后在网页端"客户端管理"页面添加客户端时填写所有必要的配置即可：
- **用户客户端**：填写 `API_ID`、`API_HASH`、`PHONE_NUMBER`
- **机器人客户端**：填写 `BOT_TOKEN`、`ADMIN_USER_ID`，以及可选的 `API_ID`、`API_HASH`

---

### Q3: 配置存储在哪里？

**A:** 
- **网页端配置**：存储在数据库中（`./data/bot.db`），持久化保存
- **环境变量配置**：仅在容器运行时生效，重启后需要重新加载

---

### Q4: 如何迁移配置？

**A:** 
- **备份网页端配置**：备份 `./data/bot.db` 文件
- **备份环境变量配置**：备份 `.env` 或 `docker-compose.yml` 文件

---

### Q5: 启动时提示配置警告怎么办？

**A:** 警告不会阻止系统启动。如果你使用网页端配置，可以忽略这些警告：
```
⚠️  全局 API_ID 未设置，将使用客户端配置（网页端添加时设置）
⚠️  全局 API_HASH 未设置，将使用客户端配置（网页端添加时设置）
```

这表示系统会优先使用你在网页端添加的客户端配置。

---

### Q6: Bot 客户端会使用哪个 API_ID 和 API_HASH？

**A:** Bot 客户端的 API 配置遵循以下优先级：

1. **客户端配置（最高优先级）**：如果在网页端添加 Bot 时填写了 `API_ID` 和 `API_HASH`，则使用该配置
2. **全局配置（fallback）**：如果网页端留空，则使用环境变量中的全局 `API_ID` 和 `API_HASH`

**推荐做法：**
- 🌟 **多 Bot 独立 API**：为每个 Bot 配置不同的 API 凭证，避免 Telegram 的速率限制
- 💡 **简化部署**：在环境变量中设置全局 API 凭证，所有 Bot 共享（适合小规模使用）

**示例场景：**

**场景 1：多 Bot 独立配置**
```bash
# docker-compose.yml 中不设置 API_ID 和 API_HASH（或留空）
API_ID=
API_HASH=

# 网页端添加 Bot1
Bot1:
  API_ID: 1234567
  API_HASH: aaa...
  BOT_TOKEN: 111:AAA...

# 网页端添加 Bot2
Bot2:
  API_ID: 7654321
  API_HASH: bbb...
  BOT_TOKEN: 222:BBB...
```

**场景 2：全局配置共享**
```bash
# docker-compose.yml 中设置全局配置
API_ID=1234567
API_HASH=aaa...

# 网页端添加 Bot1（API_ID 和 API_HASH 留空）
Bot1:
  BOT_TOKEN: 111:AAA...
  ADMIN_USER_ID: 123456789

# 网页端添加 Bot2（API_ID 和 API_HASH 留空）
Bot2:
  BOT_TOKEN: 222:BBB...
  ADMIN_USER_ID: 987654321

# 两个 Bot 共享全局的 API_ID=1234567 和 API_HASH=aaa...
```

---

---

### Q7: 为什么用户客户端登录时提示 "user 不存在"？

**A:** 这通常是因为 **API_ID/API_HASH 与 session 文件不匹配**导致的。

**Telegram 的 session 机制：**
- Telegram 的 session 文件与创建它时使用的 `API_ID` 绑定
- 如果你更改了 `API_ID` 但保留了旧的 session 文件，Telegram 会认为这是不同的应用，从而报错 "user 不存在"

**已修复（v1.1.1+）：** ✅
- 系统会自动检测 API_ID 变化
- 当检测到不匹配时，自动删除旧的 session 文件
- 你可以使用新的 API 凭证重新登录，无需手动删除文件

**旧版本解决方法：**
1. 删除旧的 session 文件（位于 `./sessions/` 目录）
2. 使用新的 API_ID 重新登录

---

### Q8: 机器人客户端无法启动怎么办？

**A:** 检查以下几点：

1. **Bot Token 是否正确：** 从 @BotFather 获取有效的 Bot Token
2. **API_ID 和 API_HASH：**
   - 如果网页端添加 Bot 时**填写了 API_ID/API_HASH**，确保它们正确
   - 如果网页端**留空**，确保环境变量中的全局 `API_ID` 和 `API_HASH` 正确
3. **网络连接：** 如果在国内，确保配置了代理
4. **查看日志：** 检查 `./logs/enhanced_bot.log` 获取详细错误信息

**常见错误：**
- ❌ `缺少Bot Token` → 网页端或环境变量中提供 BOT_TOKEN
- ❌ `缺少API ID或API Hash` → 网页端填写或在环境变量中配置
- ❌ `Telegram服务器连接失败` → 检查网络和代理配置

---

## 📚 相关文档

- [部署指南](DEPLOYMENT.md)
- [本地开发](local-dev/README.md)
- [版本管理](docs/VERSION_MANAGEMENT.md)

---

## 🐛 已知问题修复记录

### v1.1.1 修复
- ✅ **修复 Bot 客户端启动失败：** Bot 现在支持独立 API 配置，不再强制依赖全局配置
- ✅ **修复用户登录 "user 不存在" 错误：** 自动检测并清理 API_ID 不匹配的 session 文件
- ✅ **优化配置灵活性：** 支持纯网页端配置，无需配置环境变量即可使用


