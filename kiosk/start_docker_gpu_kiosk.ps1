<#
Поднимает бэкенд в Docker (GPU-профиль) и сразу открывает дашборд в режиме
киоска Chrome на этой же Windows-машине — одной командой.

Почему это отдельный скрипт: `docker compose --profile gpu up --build` сам по
себе НЕ открывает браузер — эта команда только поднимает бэкенд-контейнер
(Flask/Waitress) внутри Docker Desktop, и если её запустить в обычном
(foreground) режиме, терминал блокируется логами контейнера и до Chrome дело
не доходит вообще. Открытие Chrome в kiosk-режиме — отдельный шаг
(start_kiosk.ps1), который должен выполняться на Windows-хосте ПОСЛЕ того, как
бэкенд поднялся и прошёл healthcheck.

Этот скрипт: 1) поднимает docker compose с флагом -d (detached, не блокирует
терминал), 2) передаёт управление start_kiosk.ps1, который сам дожидается
/health (см. -WaitForBackendSec) и затем открывает Chrome в kiosk-режиме с
автоперезапуском.

Использование:
    cd kiosk
    .\start_docker_gpu_kiosk.ps1                              # сборка + запуск + kiosk на localhost:8000
    .\start_docker_gpu_kiosk.ps1 -NoBuild                     # без пересборки образа (docker compose up -d)
    .\start_docker_gpu_kiosk.ps1 -Url "http://192.168.0.85"   # фронт вынесен на отдельный сервер
#>
param(
    [string]$Url = "http://localhost:8000",
    [switch]$NoBuild,
    [int]$WaitForBackendSec = 300
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $repoRoot
try {
    $composeArgs = @("compose", "--profile", "gpu", "up", "-d")
    if (-not $NoBuild) { $composeArgs += "--build" }

    Write-Host "Запуск: docker $($composeArgs -join ' ')"
    & docker @composeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose завершился с ошибкой (код $LASTEXITCODE). Kiosk не запускается."
    }
} finally {
    Pop-Location
}

& (Join-Path $PSScriptRoot "start_kiosk.ps1") -Url $Url -WaitForBackendSec $WaitForBackendSec
