# Registers the Robot agent as a Windows scheduled task.
# Run in a PowerShell opened as administrator, from inside the agent folder.
# The task itself runs without elevated privileges: shutting the PC down does not need administrator.
#   powershell -ExecutionPolicy Bypass -File .\install_task.ps1
# ASCII characters only on purpose (avoids PowerShell encoding problems).
param(
    [ValidateSet("Startup", "Logon")]
    [string]$Trigger = "Startup",
    [string]$TaskName = "RobotAgente"
)

$ErrorActionPreference = "Stop"

$folder = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $python) { throw "pythonw.exe not found on PATH. Install Python from python.org with the PATH option checked." }
if ($python -like "*WindowsApps*") { throw "The pythonw found is the Microsoft Store shortcut. Install Python from python.org." }

$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute $python -Argument "-m robot_agent" -WorkingDirectory $folder
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

if ($Trigger -eq "Startup") {
    # Runs before logon, under your own account: it is the one that keeps the key in the Credential Manager.
    # Windows asks for the account password to store in the task; it is never written to any file.
    $credential = Get-Credential -UserName $user -Message "Your Windows account password (stored only in Task Scheduler)"
    $startTrigger = New-ScheduledTaskTrigger -AtStartup
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $startTrigger -Settings $settings `
        -User $user -Password $credential.GetNetworkCredential().Password -RunLevel Limited -Force | Out-Null
} else {
    # Alternative without a stored password: it only runs after you sign in.
    $logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $logonTrigger -Settings $settings `
        -Principal $principal -Force | Out-Null
}

Start-ScheduledTask -TaskName $TaskName
Write-Host "Task '$TaskName' registered ($Trigger) and started."
Write-Host "Agent log: $env:LOCALAPPDATA\robot-agente\agent.log"
