param([Parameter(Mandatory)][string]$AppDirectory)

$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($AppDirectory)
if (-not [IO.File]::Exists([IO.Path]::Combine($root, 'main.py'))) {
    throw 'ORBIT Desktop program files were not found.'
}
foreach ($owned in @('runtime', 'orbit\__pycache__')) {
    $target = '\\?\' + [IO.Path]::Combine($root, $owned)
    if ([IO.Directory]::Exists($target)) {
        [IO.Directory]::Delete($target, $true)
    }
}
