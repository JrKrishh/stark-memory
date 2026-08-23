param(
  [string]$Title = "stark-memory",
  [string]$Msg = "shield intercepted a command"
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$balloon = New-Object System.Windows.Forms.NotifyIcon
$balloon.Icon = [System.Drawing.SystemIcons]::Warning
$balloon.BalloonTipTitle = $Title
$balloon.BalloonTipText = $Msg
$balloon.Visible = $true
$balloon.ShowBalloonTip(6000)

Start-Sleep -Seconds 7
$balloon.Dispose()
