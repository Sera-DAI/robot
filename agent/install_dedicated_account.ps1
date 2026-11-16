# Installs the Robot agent as a scheduled task under a dedicated local account,
# so that voice shutdown also works while the PC sits at the login screen (D25).
# Run in a PowerShell opened as administrator, from inside the agent folder:
#   powershell -ExecutionPolicy Bypass -File .\install_dedicated_account.ps1
# To undo everything: the same command with -Remove.
# ASCII characters only on purpose (avoids PowerShell encoding problems).
param(
    [string]$Account = "robot-agente-svc",
    [string]$TaskName = "RobotAgente",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { throw "Open PowerShell as administrator." }

$appFolder = Join-Path $env:ProgramData "robot-agente\app"
$hiddenAccounts = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    if (Get-LocalUser -Name $Account -ErrorAction SilentlyContinue) { Remove-LocalUser -Name $Account }
    Remove-ItemProperty -Path $hiddenAccounts -Name $Account -ErrorAction SilentlyContinue
    if (Test-Path (Split-Path -Parent $appFolder)) { Remove-Item -Recurse -Force (Split-Path -Parent $appFolder) }
    Write-Host "Task, account '$Account' and agent copy removed."
    Write-Host "The account profile folder under $env:SystemDrive\Users can be deleted by hand."
    return
}

# 1. Python: the dedicated account must be able to read it, so it cannot live in the owner's profile.
$pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
$python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (-not $pythonw -or -not $python) { throw "Python not found on PATH. Install Python from python.org (for all users) with the PATH option checked." }
if ($pythonw -like "*WindowsApps*") { throw "The Python found is the Microsoft Store shortcut. Install Python from python.org." }
if ($pythonw -like "$env:USERPROFILE\*") { throw "Python is inside your profile, which the dedicated account cannot read. Reinstall it from python.org with 'Install for all users'." }

# 2. Copy the code to a folder that only administrators can change (the dedicated account only reads it).
$source = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "robot_agent"
if (-not (Test-Path $source)) { throw "robot_agent folder not found next to this script." }
if (Test-Path $appFolder) { Remove-Item -Recurse -Force $appFolder }
New-Item -ItemType Directory -Force -Path $appFolder | Out-Null
Copy-Item -Recurse -Force $source (Join-Path $appFolder "robot_agent")
Get-ChildItem -Recurse -Directory -Filter "__pycache__" $appFolder | Remove-Item -Recurse -Force

# 3. Plain local account with a random password that is never shown or written to a file.
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
$bytes = New-Object byte[] 48
$rng.GetBytes($bytes)
$plainPassword = -join ($bytes | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
$password = ConvertTo-SecureString $plainPassword -AsPlainText -Force

if (Get-LocalUser -Name $Account -ErrorAction SilentlyContinue) {
    Set-LocalUser -Name $Account -Password $password
} else {
    New-LocalUser -Name $Account -Password $password -PasswordNeverExpires -UserMayNotChangePassword -AccountNeverExpires `
        -Description "Unprivileged account that runs the Robot agent" | Out-Null
    $usersGroup = Get-LocalGroup -SID "S-1-5-32-545"
    Add-LocalGroupMember -Group $usersGroup -Member $Account
}
# Hide the account from the login screen.
if (-not (Test-Path $hiddenAccounts)) { New-Item -Path $hiddenAccounts -Force | Out-Null }
New-ItemProperty -Path $hiddenAccounts -Name $Account -PropertyType DWord -Value 0 -Force | Out-Null

# 4. Permissions: administrators and SYSTEM control the folder; the dedicated account can only read and run.
icacls $appFolder /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" "${Account}:(OI)(CI)RX" | Out-Null

# 5. Scheduled task at startup under the dedicated account (the password stays only in Task Scheduler).
$action = New-ScheduledTaskAction -Execute $pythonw -Argument "-m robot_agent" -WorkingDirectory $appFolder
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew
$trigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -User ".\$Account" -Password $plainPassword -RunLevel Limited -Force | Out-Null

# 6. Access key in the dedicated account's Credential Manager: the setup runs as that account, in another window.
Write-Host "Another window will open to enter the queue URL, key ID and secret of the robot-agente key."
$credential = New-Object System.Management.Automation.PSCredential(".\$Account", $password)
Start-Process -FilePath $python -ArgumentList "-m", "robot_agent.configure" -WorkingDirectory $appFolder `
    -Credential $credential -LoadUserProfile -Wait
$plainPassword = $null

Start-ScheduledTask -TaskName $TaskName
Write-Host "Task '$TaskName' registered under account '$Account' and started."
Write-Host "Agent log: $env:SystemDrive\Users\$Account\AppData\Local\robot-agente\agent.log"
Write-Host "If the old credential exists in your own account, delete it: cmdkey /delete:robot-agente"
Write-Host "After updating the repository code, run this script again to recopy the agent."
