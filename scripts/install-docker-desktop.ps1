# 在 Windows 上启动 Docker Desktop 并提示 WSL 集成（需用户确认设置项）
$ErrorActionPreference = "Stop"

$dockerExe = "${env:ProgramFiles}\Docker\Docker\Docker Desktop.exe"
if (-not (Test-Path $dockerExe)) {
    Write-Host "未检测到 Docker Desktop。请安装:"
    Write-Host "  https://docs.docker.com/desktop/setup/install/windows-install/"
    exit 1
}

Write-Host "正在启动 Docker Desktop..."
Start-Process $dockerExe

Write-Host @"

请在 Docker Desktop 图形界面中确认（仅需一次）:

  1. 等待左下角/engine 状态为 Running（引擎已启动）
  2. Settings (齿轮) → General
     - [x] Use the WSL 2 based engine
  3. Settings → Resources → WSL Integration
     - [x] Enable integration with my default WSL distro
     - [x] 打开你使用的 Ubuntu 发行版开关

然后在 WSL 终端执行:

  cd /mnt/f/AI_Agent/Duliu
  bash scripts/wsl-setup-docker.sh
  source ~/.bashrc
  bash scripts/wsl-duliu-up.sh

浏览器访问: http://localhost:8000

"@
