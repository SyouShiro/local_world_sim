# compile2exe

本文档记录如何在 Windows 下使用 `PyInstaller` 将本项目打包为可分发的 `exe`，并通过 `PyArmor` 做代码混淆（常被称为“加密”打包）。

## 1. 先说结论（重要）

- 仅用 `PyInstaller` 不能真正加密 Python 源码，只是打包。
- 想提高逆向门槛，需要在打包前使用 `PyArmor` 做混淆。
- 即使混淆，也不是绝对不可逆，只是增加破解成本。

## 2. 环境准备

在项目根目录执行（推荐 PowerShell）：

```powershell
conda run -n local_world_sim python -m pip install --upgrade pip
conda run -n local_world_sim python -m pip install pyinstaller pyarmor
```

确认关键目录存在：

- `backend/app`
- `frontend`
- `backend/.env`（或至少有 `backend/.env.example`）

## 3. 创建打包入口脚本

本仓库已内置打包入口：`build_tools/pack_entry.py`。

它会做三件事：
- 启动后端（固定 `127.0.0.1:8000`，以匹配前端写死的 API_BASE / WebSocket 地址）。
- 启动前端静态服务器（默认 `127.0.0.1:5500`，如果被占用会自动换一个空闲端口）。
- 自动打开浏览器进入前端页面。

额外说明：
- 若运行目录没有 `.env` 或缺少 `APP_SECRET_KEY`，它会自动生成并写入 `.env`（不会打印密钥）。
- 数据库 `worldline.db` 默认会落在 exe 同目录（方便“关掉再开，世界还在”）。

## 4. 先混淆（PyArmor）

```powershell
conda run -n local_world_sim pyarmor gen -O build/obf -r build_tools/pack_entry.py backend/app
```

完成后，`build/obf` 下会出现混淆后的脚本和 `pyarmor_runtime_*` 运行时目录。

## 5. 再打包（PyInstaller）

```powershell
conda run -n local_world_sim pyinstaller `
  --noconfirm `
  --clean `
  --onefile `
  --name worldline_sim `
  --paths build/obf `
  --add-data "frontend;frontend" `
  --hidden-import app `
  --hidden-import app.main `
  --hidden-import app.api `
  --hidden-import app.api.session `
  --hidden-import app.api.timeline `
  --hidden-import app.api.provider `
  --hidden-import app.api.branch `
  --hidden-import app.api.websocket `
  --collect-all uvicorn `
  --collect-all fastapi `
  --collect-all sqlalchemy `
  --collect-all aiosqlite `
  --collect-all pydantic `
  --collect-all pydantic_settings `
  build/obf/pack_entry.py
```

产物在：

- `dist/worldline_sim.exe`

## 5.1 推荐：直接用一键脚本

仓库内置了 PowerShell 脚本：`build_tools/build_exe.ps1`，可以一键完成（含可选混淆）。
脚本会自动扫描 `app` 包并生成完整 `--hidden-import` 列表，避免 `ModuleNotFoundError: No module named 'app.api'` 这类问题。

```powershell
.\build_tools\build_exe.ps1
```

不做混淆（只打包）：
```powershell
.\build_tools\build_exe.ps1 -NoObf
```

不显示控制台窗口（双击更“像软件”，但出错不方便看日志）：
```powershell
.\build_tools\build_exe.ps1 -NoConsole
```

## 6. 运行与分发建议

### 6.1 本机运行

1. 直接启动 `dist/worldline_sim.exe`（或你自定义的名字）。
2. 它会自动打开浏览器进入前端页面。

### 6.2 推荐分发目录结构

```text
release/
  worldline_sim.exe
  (首次运行后自动生成 .env / worldline.db)
```

## 7. 常见问题

### 7.1 启动时报 `APP_SECRET_KEY must be set`

- 现在 `worldline_sim.exe` 会自动生成 `.env` 并写入 `APP_SECRET_KEY`，一般不会再遇到。
- 如果你想手动指定：在 exe 同目录放置 `.env` 并设置 `APP_SECRET_KEY`。

### 7.2 `ModuleNotFoundError` / 缺少依赖

- 给 `PyInstaller` 增加 `--collect-all <package>`。
- 删除 `build/`、`dist/` 后重新执行打包命令。

### 7.3 前端无法连接后端

- 后端固定启动在 `127.0.0.1:8000`（前端写死），因此：
  - 确认 `8000` 端口未被占用。
  - 确认防火墙未拦截本机回环地址。

## 8. 安全加固建议（可选）

- 使用较新的 `PyArmor` 版本并开启更高混淆级别。
- 对发布包做代码签名（Windows 证书）。
- 不要把真实 `API Key`、生产 `.env`、数据库文件打进发布包。
