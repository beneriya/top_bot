# setup_backup_task.ps1
# Энэ файлыг нэг удаа ажиллуулж Task Scheduler тохируулна
# Хэрхэн ажиллуулах: файл дээр баруун товш → "Run with PowerShell"

$taskName   = "TOP Bot Daily Backup"
$scriptPath = "C:\Users\Lenovo\Documents\discord_arman\bot\backup.py"
$workDir    = "C:\Users\Lenovo\Documents\discord_arman\bot"

# Python байгаа эсэхийг шалгах
$pythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonPath) {
    Write-Host "❌ Python олдсонгүй! Python суулгасан эсэхээ шалгана уу." -ForegroundColor Red
    Read-Host "Enter дарж гарна уу"
    exit 1
}

Write-Host "✅ Python олдлоо: $pythonPath" -ForegroundColor Green

# Task үүсгэх
$action   = New-ScheduledTaskAction `
    -Execute    $pythonPath `
    -Argument   "`"$scriptPath`"" `
    -WorkingDirectory $workDir

$trigger  = New-ScheduledTaskTrigger -Daily -At "03:00"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask `
    -TaskName $taskName `
    -Action   $action `
    -Trigger  $trigger `
    -Settings $settings `
    -Description "TOP Bot өдөр бүр 03:00-д bot.db-г нөөцөлнө" `
    -Force | Out-Null

Write-Host ""
Write-Host "✅ Task амжилттай үүслээ!" -ForegroundColor Green
Write-Host "   Нэр    : $taskName"    -ForegroundColor Cyan
Write-Host "   Цаг    : Өдөр бүр 03:00" -ForegroundColor Cyan
Write-Host "   Script : $scriptPath"  -ForegroundColor Cyan
Write-Host ""
Write-Host "Шалгах: Task Scheduler → Task Scheduler Library → '$taskName'" -ForegroundColor Yellow
Read-Host "Enter дарж гарна уу"
