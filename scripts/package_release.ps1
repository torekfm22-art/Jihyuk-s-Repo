# SPC 공정능력 분석 — 타 PC 배포용 ZIP 생성
param(
    [switch]$Build
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Utf8File {
    param([string]$Path, [string[]]$Lines)
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllLines($Path, $Lines, $utf8)
}

$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

$ReleaseDir = Join-Path $Root "release"
$DeployDir = Join-Path $Root "deploy"

function Find-DistFolder {
    $distRoot = Join-Path $Root "dist"
    if (-not (Test-Path $distRoot)) { return $null }
    $exes = Get-ChildItem -Path $distRoot -Recurse -Filter "SPC_*.exe" -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Directory.Name -ne "_internal" }
    if ($exes) {
        return $exes[0].Directory
    }
    return $null
}

function Get-AppVersion {
    $vf = Join-Path $Root "VERSION"
    if (Test-Path $vf) {
        return (Get-Content $vf -TotalCount 1).Trim()
    }
    return "1.0.0"
}

if ($Build) {
    Write-Host "[1/4] EXE 빌드 (build_exe.bat)..." -ForegroundColor Cyan
    $bat = Join-Path $Root "build_exe.bat"
    if (-not (Test-Path $bat)) { throw "build_exe.bat 없음" }
    cmd /c "`"$bat`" nopause"
    if ($LASTEXITCODE -ne 0) { throw "빌드 실패 (exit $LASTEXITCODE)" }
}

$DistFolder = Find-DistFolder
if (-not $DistFolder) {
    throw "배포 폴더가 없습니다. 먼저 build_exe.bat 을 실행하세요.`n  (dist 아래 SPC_*.exe 가 있어야 합니다)"
}
$DistDir = $DistFolder.FullName
$AppName = $DistFolder.Name
$MainExe = Get-ChildItem -Path $DistDir -Filter "SPC_*.exe" -File | Select-Object -First 1
if (-not $MainExe) { throw "exe 파일을 찾을 수 없습니다: $DistDir" }

$Version = Get-AppVersion
$DateTag = Get-Date -Format "yyyyMMdd"
$ZipBase = "${AppName}_v${Version}_Win64_${DateTag}"
$Staging = Join-Path $ReleaseDir "staging\$AppName"

Write-Host "[2/4] 배포 폴더 구성..." -ForegroundColor Cyan
if (Test-Path $Staging) { Remove-Item $Staging -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Staging | Out-Null

# dist 전체 복사 (exe + _internal)
robocopy $DistDir $Staging /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
if ($LASTEXITCODE -ge 8) { throw "파일 복사 실패 (robocopy $LASTEXITCODE)" }

# data 폴더
foreach ($sub in @("input", "output", "output\charts")) {
    $p = Join-Path $Staging "data\$sub"
    New-Item -ItemType Directory -Force -Path $p | Out-Null
}
$readmeInput = Join-Path $Staging "data\input\README.txt"
Write-Utf8File -Path $readmeInput -Lines @(
    "MES/QMS Excel: GUI '+' button to attach files.",
    "You do not need to copy files into this folder.",
    ""
)

# Deploy extras (ASCII filenames in script for encoding safety)
Copy-Item (Join-Path $Root "DISTRIBUTE.txt") (Join-Path $Staging "DISTRIBUTE.txt") -Force
Copy-Item (Join-Path $DeployDir "IT_GUIDE.txt") (Join-Path $Staging "IT_GUIDE.txt") -Force
Copy-Item (Join-Path $DeployDir "RUN_SPC.bat") (Join-Path $Staging "RUN_SPC.bat") -Force
Copy-Item (Join-Path $DeployDir "CREATE_DESKTOP_SHORTCUT.bat") (Join-Path $Staging "CREATE_DESKTOP_SHORTCUT.bat") -Force
$quickStart = Join-Path $DeployDir "배포_빠른시작.txt"
if (Test-Path $quickStart) {
    Copy-Item $quickStart (Join-Path $Staging "배포_빠른시작.txt") -Force
}

$verInfo = @(
    "product=SPC 공정능력 분석",
    "version=$Version",
    "platform=Windows 64bit",
    "python_required=false",
    "built=$DateTag",
    ""
) -join "`r`n"
Write-Utf8File -Path (Join-Path $Staging "version.txt") -Lines ($verInfo -split "`r?`n")

Write-Host "[3/4] ZIP 압축..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
$ZipPath = Join-Path $ReleaseDir "$ZipBase.zip"
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }

# Compress-Archive는 상위 폴더 구조 포함 → staging\AppName 내용을 zip 루트에
$tempZipParent = Join-Path $ReleaseDir "_zipwork"
if (Test-Path $tempZipParent) { Remove-Item $tempZipParent -Recurse -Force }
New-Item -ItemType Directory -Force -Path (Join-Path $tempZipParent $AppName) | Out-Null
robocopy $Staging (Join-Path $tempZipParent $AppName) /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
Compress-Archive -Path (Join-Path $tempZipParent $AppName) -DestinationPath $ZipPath -CompressionLevel Optimal -Force
Remove-Item $tempZipParent -Recurse -Force

$sizeMb = [math]::Round((Get-Item $ZipPath).Length / 1MB, 1)
$hash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash

$manifest = @(
    "file=$ZipBase.zip",
    "size_mb=$sizeMb",
    "sha256=$hash",
    "created=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
    ""
) -join "`r`n"
Write-Utf8File -Path (Join-Path $ReleaseDir "${ZipBase}.manifest.txt") -Lines ($manifest -split "`r?`n")

Write-Host "[4/4] 완료" -ForegroundColor Green
Write-Host ""
Write-Host "  배포 ZIP: $ZipPath"
Write-Host "  크기: 약 ${sizeMb} MB"
Write-Host "  SHA256: $hash"
Write-Host ""
Write-Host "  타 PC 설치: ZIP 복사 → 압축 해제 → 실행_SPC.bat 또는 exe 실행"
Write-Host "  IT 담당자: IT_배포안내.txt 참고"
Write-Host ""
