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

在项目根目录新建 `build_tools/pack_entry.py`：

```python
from __future__ import annotations

import os
import uvicorn

from app.main import create_app


def main() -> None:
    host = os.getenv("APP_HOST", "127.0.0.1")
    port = int(os.getenv("APP_PORT", "8000"))
    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
```

> 说明：这个入口只负责后端 API。前端仍建议保留 `frontend` 静态目录，通过浏览器访问。

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
  --name worldline_backend `
  --paths build/obf `
  --collect-all uvicorn `
  --collect-all fastapi `
  --collect-all sqlalchemy `
  --collect-all aiosqlite `
  --collect-all pydantic `
  --collect-all pydantic_settings `
  build/obf/pack_entry.py
```

产物在：

- `dist/worldline_backend.exe`

## 6. 运行与分发建议

### 6.1 本机运行

1. 准备 `.env`（至少设置 `APP_SECRET_KEY`）。
2. 启动 `worldline_backend.exe`。
3. 打开前端：`frontend/index.html`（建议通过静态服务器访问）。

### 6.2 推荐分发目录结构

```text
release/
  worldline_backend.exe
  frontend/
  backend/.env.example
  start_frontend.bat
```

可选 `start_frontend.bat`：

```bat
@echo off
python -m http.server 5500 -d frontend
```

## 7. 常见问题

### 7.1 启动时报 `APP_SECRET_KEY must be set`

- 在运行目录放置 `.env` 并设置 `APP_SECRET_KEY`。
- 或在系统环境变量里设置 `APP_SECRET_KEY`。

### 7.2 `ModuleNotFoundError` / 缺少依赖

- 给 `PyInstaller` 增加 `--collect-all <package>`。
- 删除 `build/`、`dist/` 后重新执行打包命令。

### 7.3 前端无法连接后端

- 检查 `frontend/js/api.js` 的 `API_BASE` 是否与 `APP_HOST/APP_PORT` 一致。
- 检查防火墙与端口占用。

## 8. 安全加固建议（可选）

- 使用较新的 `PyArmor` 版本并开启更高混淆级别。
- 对发布包做代码签名（Windows 证书）。
- 不要把真实 `API Key`、生产 `.env`、数据库文件打进发布包。
