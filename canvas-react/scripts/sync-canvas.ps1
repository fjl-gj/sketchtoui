$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sourceRoot = Join-Path $projectRoot "..\fixtures\sketch\test_001\test"
$sourceCanvas = Join-Path $sourceRoot "canvas"
$sourceImages = Join-Path $sourceRoot "images"
$publicRoot = Join-Path $projectRoot "public"
$targetCanvas = Join-Path $publicRoot "canvas"
$targetImages = Join-Path $publicRoot "sketch\images"

if (-not (Test-Path -LiteralPath $sourceCanvas)) {
    throw "Canvas source does not exist: $sourceCanvas"
}
if (-not (Test-Path -LiteralPath $sourceImages)) {
    throw "Image source does not exist: $sourceImages"
}

New-Item -ItemType Directory -Path $targetCanvas -Force | Out-Null
New-Item -ItemType Directory -Path $targetImages -Force | Out-Null
Copy-Item -Path (Join-Path $sourceCanvas "*") -Destination $targetCanvas -Recurse -Force
Copy-Item -Path (Join-Path $sourceImages "*") -Destination $targetImages -Recurse -Force
Write-Output "Canvas data synchronized to $publicRoot"
