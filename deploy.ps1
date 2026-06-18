# Обёртка для запуска deploy.sh из PowerShell через Git Bash (НЕ WSL).
# Использование:
#   .\deploy.ps1 backend
#   .\deploy.ps1 backend --build
#   .\deploy.ps1 frontend
#   .\deploy.ps1 all
#
# WSL-bash (C:\Windows\System32\bash.exe) НЕ подходит: у него свои ssh-ключи.
# Поэтому находим именно Git Bash рядом с git.exe.

function Find-GitBash {
    $candidates = @(
        "C:\Program Files\Git\bin\bash.exe",
        "C:\Program Files (x86)\Git\bin\bash.exe",
        "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe"
    )
    # Также пробуем вывести из расположения git.exe
    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($git) {
        $gitRoot = Split-Path (Split-Path $git.Source)   # ...\Git
        $candidates += (Join-Path $gitRoot "bin\bash.exe")
    }
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    throw "Git Bash не найден. Установите Git for Windows или запустите deploy.sh из Git Bash вручную."
}

$bash = Find-GitBash
$script = Join-Path $PSScriptRoot "deploy.sh"
# docker/ssh пишут прогресс в stderr; конвертируем потоки в обычный текст,
# чтобы PowerShell не принимал это за фатальную ошибку. Код возврата берём от bash.
& $bash $script @args 2>&1 | ForEach-Object { "$_" }
exit $LASTEXITCODE
