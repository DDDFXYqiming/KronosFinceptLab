# KronosFinceptLab 启动指南

## Windows 双击启动（推荐）

直接双击 `start.bat` 文件即可一键启动：

1. **API 后端** — 在新窗口中运行于 http://localhost:8000
2. **Web 前端** — 在新窗口中运行于 http://localhost:3000

启动完成后会自动打开浏览器。

## WSL/Linux 命令行启动

```bash
./start.sh
```

按 `Ctrl+C` 停止所有服务。

## 手动启动

### 启动 API 后端

```bash
# Windows
set PYTHONPATH=src
python -m kronos_fincept.api.app

# WSL/Linux
PYTHONPATH=src python3 -m kronos_fincept.api.app
```

### 启动 Web 前端

```bash
cd web
npm install  # 首次运行需要
npm run dev
```

## 访问地址

| 服务 | 地址 |
|------|------|
| Web 前端 | http://localhost:3000 |
| API 后端 | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |

## 停止服务

### Windows
- 关闭 "KronosFinceptLab API" 和 "KronosFinceptLab Web" 两个命令行窗口

### WSL/Linux
- 在运行 `start.sh` 的终端按 `Ctrl+C`

## 常见问题

### 端口被占用
如果端口 8000 或 3000 被占用，可以：
- 关闭占用端口的程序
- 或修改启动脚本中的端口号

### Python 找不到
确保 Python 3.11+ 已安装并添加到 PATH 环境变量。

### Node.js 找不到
确保 Node.js 18+ 已安装并添加到 PATH 环境变量。

### npm install 失败
尝试清除缓存：
```bash
cd web
rm -rf node_modules package-lock.json
npm install
```
