function Test-BuildPythonCandidate {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [string[]]$PrefixArguments = @(),
        [Parameter(Mandatory = $true)][string]$Description
    )

    try {
        $VersionText = & $Executable @PrefixArguments -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" 2>$null
        if ($LASTEXITCODE -ne 0) {
            return $null
        }
        $Version = [version]$VersionText.Trim()
        if ($Version -lt [version]"3.11") {
            return $null
        }
        return [pscustomobject]@{
            Executable = $Executable
            PrefixArguments = [string[]]$PrefixArguments
            Version = $Version
            Description = $Description
        }
    } catch {
        return $null
    }
}

function Resolve-BuildPython {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [string]$PythonPath
    )

    $Tried = [System.Collections.Generic.List[string]]::new()

    # 1. Explicit -PythonPath override.
    if ($PythonPath) {
        $Tried.Add("-PythonPath=$PythonPath")
        if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
            throw "The specified Python executable was not found: $PythonPath"
        }
        $Candidate = Test-BuildPythonCandidate -Executable $PythonPath -Description "-PythonPath"
        if ($null -eq $Candidate) {
            throw "-PythonPath must point to Python 3.11 or newer: $PythonPath"
        }
        return $Candidate
    }

    # 2. Repository-local .venv.
    $VenvPython = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
    $Tried.Add($VenvPython)
    if (Test-Path -LiteralPath $VenvPython -PathType Leaf) {
        $Candidate = Test-BuildPythonCandidate -Executable $VenvPython -Description ".venv"
        if ($null -ne $Candidate) {
            return $Candidate
        }
    }

    # 3. Windows py.exe launcher, newest supported interpreter first.
    $Launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($null -ne $Launcher) {
        foreach ($Selector in @("-3.13", "-3.12", "-3.11")) {
            $Tried.Add("$($Launcher.Source) $Selector")
            $Candidate = Test-BuildPythonCandidate -Executable $Launcher.Source -PrefixArguments @($Selector) -Description "py.exe $Selector"
            if ($null -ne $Candidate) {
                return $Candidate
            }
        }
    }

    # 4. python from PATH.
    $Tried.Add("Get-Command python")
    $PathPython = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $PathPython) {
        $Candidate = Test-BuildPythonCandidate -Executable $PathPython.Source -Description "PATH python"
        if ($null -ne $Candidate) {
            return $Candidate
        }
    }

    throw "Python 3.11 or newer was not found. Tried: $($Tried -join '; '). Configure -PythonPath, .venv, py.exe, or PATH."
}
