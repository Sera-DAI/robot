# Registra o agente do Robot como tarefa agendada do Windows.
# Rode em um PowerShell aberto como administrador, de dentro da pasta agente.
# A tarefa em si roda sem privilegio elevado: desligar o PC nao exige administrador.
#   powershell -ExecutionPolicy Bypass -File .\instalar_tarefa.ps1
# Arquivo so com caracteres ASCII de proposito (evita problema de codificacao no PowerShell).
param(
    [ValidateSet("Inicializacao", "Logon")]
    [string]$Gatilho = "Inicializacao",
    [string]$NomeDaTarefa = "RobotAgente"
)

$ErrorActionPreference = "Stop"

$pasta = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $python) { throw "pythonw.exe nao encontrado no PATH. Instale o Python de python.org com a opcao de PATH marcada." }
if ($python -like "*WindowsApps*") { throw "O pythonw encontrado e o atalho da Microsoft Store. Instale o Python de python.org." }

$usuario = "$env:USERDOMAIN\$env:USERNAME"
$acao = New-ScheduledTaskAction -Execute $python -Argument "-m robot_agente" -WorkingDirectory $pasta
$ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

if ($Gatilho -eq "Inicializacao") {
    # Roda antes do logon, com a conta do dono: e ela que guarda a chave no Credential Manager.
    # O Windows pede a senha da conta para guardar na tarefa; ela nao e gravada em arquivo nenhum.
    $credencial = Get-Credential -UserName $usuario -Message "Senha da sua conta do Windows (fica guardada so no Agendador de Tarefas)"
    $disparo = New-ScheduledTaskTrigger -AtStartup
    Register-ScheduledTask -TaskName $NomeDaTarefa -Action $acao -Trigger $disparo -Settings $ajustes `
        -User $usuario -Password $credencial.GetNetworkCredential().Password -RunLevel Limited -Force | Out-Null
} else {
    # Alternativa sem senha guardada: so roda depois que voce entra na conta.
    $disparo = New-ScheduledTaskTrigger -AtLogOn -User $usuario
    $principal = New-ScheduledTaskPrincipal -UserId $usuario -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $NomeDaTarefa -Action $acao -Trigger $disparo -Settings $ajustes `
        -Principal $principal -Force | Out-Null
}

Start-ScheduledTask -TaskName $NomeDaTarefa
Write-Host "Tarefa '$NomeDaTarefa' registrada ($Gatilho) e iniciada."
Write-Host "Log do agente: $env:LOCALAPPDATA\robot-agente\agente.log"
