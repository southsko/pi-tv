# partition_card.ps1 - create the exFAT data partition on a freshly flashed
# SD card, entirely from PowerShell. No diskpart, no Disk Management.
#
# Run AFTER flashing with Raspberry Pi Imager, BEFORE the Pi's first boot:
#   Right-click -> Run with PowerShell   (auto-elevates to admin)
#
# What it does:
#  * finds the SD card automatically (the disk whose boot partition
#    contains cmdline.txt) and asks you to confirm
#  * creates a data partition starting at the 8 GB mark, using the rest
#    of the card, formatted exFAT with label PITV
#  * the partition's existence also blocks Pi OS from expanding over the
#    whole card on first boot; setup.sh on the Pi reclaims the gap for
#    the OS and mounts PITV as the videos folder
#
# You can drag episodes onto the PITV drive as soon as it finishes.

$ErrorActionPreference = "Stop"

# -- self-elevate ---------------------------------------------------------
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Start-Process powershell "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# -- find the SD card by its boot partition -------------------------------
$bootDrive = $null
foreach ($v in Get-Volume | Where-Object DriveLetter) {
    if (Test-Path "$($v.DriveLetter):\cmdline.txt") { $bootDrive = $v.DriveLetter; break }
}
if (-not $bootDrive) {
    Write-Host "Couldn't find a drive containing cmdline.txt." -ForegroundColor Red
    Write-Host "Insert the freshly flashed SD card first."
    Read-Host "Press Enter to exit"; exit 1
}

$diskNumber = (Get-Partition -DriveLetter $bootDrive).DiskNumber
$disk = Get-Disk -Number $diskNumber
$sizeGB = [math]::Round($disk.Size / 1GB, 1)

Write-Host ""
Write-Host "Found SD card:" -ForegroundColor Cyan
Write-Host "  Disk $diskNumber : $($disk.FriendlyName)  ($sizeGB GB)"
Write-Host "  Boot partition: ${bootDrive}:"
Write-Host ""

if ($disk.Size -lt 10GB) {
    Write-Host "Card is smaller than 10 GB - not enough room for OS (8 GB) + data." -ForegroundColor Red
    Read-Host "Press Enter to exit"; exit 1
}
$existing = Get-Partition -DiskNumber $diskNumber
if ($existing.Count -ge 3) {
    Write-Host "This card already has $($existing.Count) partitions - data partition probably exists." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"; exit 1
}

$confirm = Read-Host "Create exFAT data partition on disk $diskNumber ($($disk.FriendlyName), $sizeGB GB)? [y/N]"
if ($confirm -notmatch '^[yY]') { Write-Host "Aborted."; exit 0 }

# -- create + format -------------------------------------------------------
Write-Host "Creating data partition at the 8 GB mark..."
$part = New-Partition -DiskNumber $diskNumber -Offset 8589934592 -UseMaximumSize -AssignDriveLetter
Start-Sleep -Seconds 2
Write-Host "Formatting as exFAT (PITV)..."
Format-Volume -Partition $part -FileSystem exFAT -NewFileSystemLabel "PITV" -Confirm:$false | Out-Null

$letter = ($part | Get-Partition).DriveLetter
Write-Host ""
Write-Host "Done! Drive ${letter}: (PITV) is ready - drag episodes onto it now if you like." -ForegroundColor Green
Write-Host "Folders you create become channels."
Write-Host ""
Write-Host "Next: eject the card, boot the Pi, then:" -ForegroundColor Green
Write-Host "  sudo apt update && sudo apt install -y git"
Write-Host "  git clone https://github.com/southsko/pi-tv.git ~/pi-tv"
Write-Host "  cd ~/pi-tv && bash setup.sh"
Read-Host "Press Enter to exit"
