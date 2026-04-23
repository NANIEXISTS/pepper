$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$targets = @(
  (Join-Path $workspace ".pytest_cache"),
  (Join-Path $workspace "trading_ai.db")
)

foreach ($target in $targets) {
  if (Test-Path -LiteralPath $target) {
    Remove-Item -LiteralPath $target -Recurse -Force
  }
}

Get-ChildItem -Path $workspace -Recurse -Directory -Filter "__pycache__" | ForEach-Object {
  Remove-Item -LiteralPath $_.FullName -Recurse -Force
}

Get-ChildItem -Path $workspace -Recurse -Include "*.pyc" -File | ForEach-Object {
  Remove-Item -LiteralPath $_.FullName -Force
}
