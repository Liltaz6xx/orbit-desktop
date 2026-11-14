param(
    [string]$Tag,
    [string]$Compiler,
    [string]$OutputDirectory,
    [switch]$InstallCompiler
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $Root 'dist' }
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

$versionSource = Get-Content -LiteralPath (Join-Path $Root 'orbit/__init__.py') -Raw
if ($versionSource -notmatch '(?m)^__version__ = "(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?"$') {
    throw 'Expected an ORBIT version such as 0.7.0-beta.2.'
}
$build = 65535
$version = "$($Matches[1]).$($Matches[2]).$($Matches[3])"
if ($Matches[4]) {
    $build = [int]$Matches[4]
    if ($build -gt 65534) { throw 'Beta number exceeds the Windows version range.' }
}
$windowsVersion = "$version.$build"
if ($build -ne 65535) { $version += "-beta.$build" }
if ($Tag -and $Tag -cne "v$version") { throw "Tag $Tag does not match ORBIT v$version." }

$stage = Join-Path $OutputDirectory 'installer-build'
New-Item -ItemType Directory -Path $stage -Force | Out-Null

function Receive-VerifiedFile($Url, $Destination, $Sha256) {
    if ((Test-Path -LiteralPath $Destination) -and (Get-FileHash -LiteralPath $Destination).Hash -eq $Sha256) {
        return
    }
    Invoke-WebRequest -Uri $Url -OutFile $Destination
    if ((Get-FileHash -LiteralPath $Destination).Hash -ne $Sha256) {
        throw "SHA-256 mismatch for $Url"
    }
}

if ($InstallCompiler -and -not $Compiler) {
    $inno = Join-Path $stage 'innosetup-6.7.4.exe'
    Receive-VerifiedFile -Destination $inno -Sha256 'a549929319f9120716677c685535ca4671e4b937b5fdc87e2585f32d8eb30e8c' -Url 'https://github.com/jrsoftware/issrc/releases/download/is-6_7_4/innosetup-6.7.4.exe'
    $innoDir = Join-Path $stage 'Inno Setup 6'
    $Compiler = Join-Path $innoDir 'ISCC.exe'
    if (-not (Test-Path -LiteralPath $Compiler)) {
        $process = Start-Process -FilePath $inno -ArgumentList @(
            '/VERYSILENT', '/NORESTART', ('/DIR="' + $innoDir + '"')
        ) -WindowStyle Hidden -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw "Inno Setup installation failed ($($process.ExitCode))." }
    }
}
if (-not $Compiler) {
    $Compiler = (Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue).Source
    if (-not $Compiler) {
        $Compiler = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6/ISCC.exe'
    }
}
if (-not (Test-Path -LiteralPath $Compiler -PathType Leaf)) {
    throw 'Install Inno Setup 6.7.4 or supply the full path to ISCC.exe with -Compiler.'
}

$uvVersion = '0.13.8'
$uvZip = Join-Path $stage "uv-$uvVersion.zip"
$uvDir = Join-Path $stage "uv-$uvVersion"
Receive-VerifiedFile -Destination $uvZip -Sha256 '529e78a9cec6cd7e3e014f7ecd8bda0c113969d4ed0f2efeedb85c30943325b8' -Url "https://github.com/astral-sh/uv/releases/download/$uvVersion/uv-x86_64-pc-windows-msvc.zip"
Expand-Archive -LiteralPath $uvZip -DestinationPath $uvDir -Force
$uv = Get-ChildItem -LiteralPath $uvDir -Filter uv.exe -Recurse -File | Select-Object -First 1
$notices = Join-Path $stage "uv-$uvVersion-NOTICES.txt"
$uvLicense = (Invoke-WebRequest "https://raw.githubusercontent.com/astral-sh/uv/$uvVersion/LICENSE-MIT").Content
Set-Content -LiteralPath $notices -Encoding utf8 -Value @("uv $uvVersion", 'https://github.com/astral-sh/uv', '', $uvLicense)

$script = Join-Path $Root 'installer/orbit.iss'
$lock = Join-Path $Root 'installer/requirements-win-x64.txt'
# The runtime changes when its locked wheels, Python build or provisioning code change.
$runtime = ((Get-FileHash -LiteralPath $lock).Hash.Substring(0, 12) + '-' +
    (Get-FileHash -LiteralPath $script).Hash.Substring(0, 12) + "-uv$uvVersion").ToLowerInvariant()

$compilerArgs = @('/Qp', "/O$OutputDirectory", "/DOrbitVersion=$version",
    "/DWindowsVersion=$windowsVersion", "/DUvExe=$($uv.FullName)", "/DUvNotices=$notices",
    "/DRuntimeId=$runtime", $script)
& $Compiler @compilerArgs
if ($LASTEXITCODE -ne 0) { throw "Installer compilation failed ($LASTEXITCODE)." }

$name = "ORBIT-Desktop-$version-Windows-x64-Setup.exe"
$exe = Join-Path $OutputDirectory $name
$hash = (Get-FileHash -LiteralPath $exe).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$exe.sha256" -Value "$hash  $name" -Encoding ascii
Write-Output $exe
