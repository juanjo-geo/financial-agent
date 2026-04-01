# setup_email_task.ps1
# Registra la tarea "Financial Agent - Email" en Windows Task Scheduler
# Ejecutar UNA SOLA VEZ como Administrador desde PowerShell

$taskName   = "Financial Agent - Email"
$batFile    = "C:\Users\Juan Jose\financial-agent\send_email.bat"
$logFile    = "C:\Users\Juan Jose\financial-agent\logs\email.log"

# Hora de ejecucion: 8:00 AM lunes a viernes
# (GitHub Actions corre ~7:00 AM, Cowork genera narrativa ~7:37 AM, este paso va despues)
$trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "08:00AM"

$action  = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$batFile`""

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName   $taskName `
    -Trigger    $trigger `
    -Action     $action `
    -Settings   $settings `
    -Principal  $principal `
    -Force

Write-Host ""
Write-Host "Tarea '$taskName' registrada correctamente." -ForegroundColor Green
Write-Host "Corre lunes a viernes a las 8:00 AM." -ForegroundColor Cyan
Write-Host ""
Write-Host "Para probar manualmente ahora, ejecuta en PowerShell:" -ForegroundColor Yellow
Write-Host "  & 'C:\Users\Juan Jose\financial-agent\send_email.bat'" -ForegroundColor White
