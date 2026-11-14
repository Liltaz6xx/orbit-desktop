# Download only official Kokoro v1.0 model files, and verify SHA-256.
# Matching files are reused. Existing files are replaced only after verification.
param([string]$AssetsDirectory = "")
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

if ([string]::IsNullOrWhiteSpace($AssetsDirectory)) {
    $AssetsDirectory = Join-Path (Split-Path -Parent $PSScriptRoot) 'assets'
}
New-Item -ItemType Directory -Path $AssetsDirectory -Force | Out-Null

$files = @(
    @{
        Name = 'kokoro-v1.0.int8.onnx'
        Url = 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.int8.onnx'
        Sha256 = 'ae315a79b623f244700e4afb9246c46a26066782e049ba174bf3ba433970ee9c'
        MinSize = 50000000
    },
    @{
        Name = 'voices-v1.0.bin'
        Url = 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin'
        Sha256 = 'bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d'
        MinSize = 20000000
    }
)

foreach ($file in $files) {
    $destination = Join-Path $AssetsDirectory $file.Name
    if (Test-Path -LiteralPath $destination -PathType Leaf) {
        if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -eq $file.Sha256) {
            Write-Host "Already present: $($file.Name)" -ForegroundColor Green
            continue
        }
        Write-Host "A verified download will replace $($file.Name)." -ForegroundColor Yellow
    }

    $temp = "$destination.$([guid]::NewGuid().ToString('N')).part"
    Write-Host "Downloading $($file.Name) from the official Kokoro release..." -ForegroundColor Cyan
    try {
        Invoke-WebRequest -Uri $file.Url -OutFile $temp -UseBasicParsing -MaximumRedirection 10
        if ((Get-Item -LiteralPath $temp).Length -lt $file.MinSize) {
            throw "File is smaller than expected, so it may be incomplete."
        }
        $actual = (Get-FileHash -LiteralPath $temp -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $file.Sha256) {
            throw "SHA-256 verification failed for $($file.Name). Expected $($file.Sha256); got $actual."
        }
        if (Test-Path -LiteralPath $destination -PathType Leaf) {
            $backup = "$temp.bak"
            [IO.File]::Replace($temp, $destination, $backup)
            Remove-Item -LiteralPath $backup -Force
        }
        else {
            [IO.File]::Move($temp, $destination)
        }
        Write-Host "Verified: $($file.Name)" -ForegroundColor Green
    }
    catch {
        if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force }
        Write-Host "Could not download $($file.Name): $_" -ForegroundColor Red
        throw
    }
}

Write-Host 'Kokoro voice assets are ready.' -ForegroundColor Green
