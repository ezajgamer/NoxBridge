# يبني نسخة NoxBridge 2 للنشر: release\NoxBridge\ (NoxBridge.exe + _internal) + release\NoxBridge-<الإصدار>.zip
# ما تحتاج بايثون ولا .NET عند اللي ينزّلها (المرقّع على .NET Framework اللي بويندوز أصلاً).
# الاستخدام: powershell -ExecutionPolicy Bypass -File tools\build-release.ps1 [-Version 2.0]
param([string]$Version = "2.0")
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$out = Join-Path $root 'release'
$app = Join-Path $out 'NoxBridge'
$build = Join-Path $out '_build'

# بيانات المستخدم (الدخول والإعدادات) بالنسخة المجرّبة محلياً — تنحفظ وترجع بعد البناء، وما تدخل الـzip
$save = Join-Path $app 'Save'
$keep = Join-Path $out '_save_keep'
if (Test-Path $save) {
    if (Test-Path $keep) { [IO.Directory]::Delete($keep, $true) }
    Move-Item $save $keep
}
if (Test-Path $app) { [IO.Directory]::Delete($app, $true) }
New-Item -ItemType Directory -Force $out, $build | Out-Null

Write-Host '• مكتبة اللعبة (NoxGame.dll)'
dotnet build (Join-Path $root 'game\NoxGame.csproj') -c Release -nologo -v q
if ($LASTEXITCODE) { throw 'فشل بناء NoxGame' }

Write-Host '• المرقّع (NoxPatcher2)'
dotnet build (Join-Path $root 'patcher\NoxPatcher2.csproj') -c Release -nologo -v q
if ($LASTEXITCODE) { throw 'فشل بناء المرقّع' }

Write-Host '• البرنامج (PyInstaller)'
if (-not (Test-Path (Join-Path $root 'app\nox.ico'))) { throw 'ناقص app\nox.ico — شغّل البرنامج مرة (يرسمها)' }
# py (ويندوز) أو python (GitHub Actions)
$python = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } else { 'python' }
& $python -m PyInstaller --noconfirm --clean --distpath $out --workpath $build (Join-Path $PSScriptRoot 'NoxBridge.spec')
if ($LASTEXITCODE) { throw 'فشل PyInstaller' }
Copy-Item (Join-Path $root 'docs\README-release.txt') (Join-Path $app 'README.txt')

$zip = Join-Path $out "NoxBridge-$Version.zip"
if (Test-Path $zip) { [IO.File]::Delete($zip) }
Compress-Archive -Path $app -DestinationPath $zip   # (tar يتعثّر بالأسماء العربية)
if (Test-Path $keep) { Move-Item $keep $save }   # بعد الـzip — ما ينشر
$dir = (Get-ChildItem $app -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
$size = (Get-Item $zip).Length / 1MB
Write-Host ("✅ المجلد {0:N1} MB · {1} ({2:N1} MB)" -f $dir, $zip, $size)
