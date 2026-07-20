param(
    [Parameter(Mandatory = $true)]
    [string]$ExePath,
    [int]$StartupSeconds = 2,
    [ValidateSet("light", "dark", "high_contrast")]
    [string]$Theme
)

$ErrorActionPreference = "Stop"

$arguments = @()
if ($Theme) {
    $arguments += "--theme-smoke=$Theme"
    $arguments += "--smoke-exit-ms=$($StartupSeconds * 1000)"
}

$process = Start-Process -FilePath $ExePath -ArgumentList $arguments -PassThru
Start-Sleep -Seconds $StartupSeconds

if ($Theme) {
    [void]$process.WaitForExit(5000)
    if (-not $process.HasExited) {
        $process.Kill()
        $process.WaitForExit()
        throw "EXE theme smoke timed out: $Theme / $ExePath"
    }
    if ($process.ExitCode -ne 0) {
        throw "EXE theme smoke failed with code $($process.ExitCode): $Theme / $ExePath"
    }
    Write-Output "EXE theme smoke ok: $Theme / $ExePath"
    exit 0
}

if ($process.HasExited) {
    throw "EXE exited too early with code $($process.ExitCode): $ExePath"
}

[void]$process.CloseMainWindow()
Start-Sleep -Seconds 1
if (-not $process.HasExited) {
    $process.Kill()
    $process.WaitForExit()
}

Write-Output "EXE smoke ok: $ExePath"
