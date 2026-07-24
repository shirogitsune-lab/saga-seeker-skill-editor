param(
    [Parameter(Mandatory = $true)]
    [string]$ExePath,
    [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"
$resolvedExe = (Resolve-Path -LiteralPath $ExePath).Path
$process = Start-Process -FilePath $resolvedExe -ArgumentList "--image-smoke" -PassThru -WindowStyle Hidden
if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
    $process.Kill()
    throw "EXE image smoke timed out: $resolvedExe"
}
if ($process.ExitCode -ne 0) {
    throw "EXE image smoke failed with code $($process.ExitCode): $resolvedExe"
}
Write-Output "EXE image smoke ok: $resolvedExe"
