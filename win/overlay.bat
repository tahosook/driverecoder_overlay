REM Define the paths
set DR_PATH=%~dp0mov
set OVERLAY_PATH=%~dp0mov\overlay
set PS_SCRIPT_PATH=%~dp0overlay1.ps1
set ZIP_PATH=%USERPROFILE%\Desktop\overlay.zip

REM Check and create 'overlay' folder if not exists
if not exist "%OVERLAY_PATH%\" (
    echo "overlay" folder does not exist. Creating...
    mkdir "%OVERLAY_PATH%"
    echo Folder created!
) else (
    echo "overlay" folder already exists.
)

REM Check and execute overlay.ps1 with PowerShell
if exist "%PS_SCRIPT_PATH%" (
    echo Executing overlay.ps1 with PowerShell...
    powershell -ExecutionPolicy Bypass -File "%PS_SCRIPT_PATH%" -dirPath "mov"

    pause
) else (
    echo overlay.ps1 does not exist in the 'mov' directory.
)

REM Zip the 'overlay' folder and move to the desktop
echo Compressing the overlay folder...
powershell -Command "Add-Type -Assembly 'System.IO.Compression.FileSystem'; [System.IO.Compression.ZipFile]::CreateFromDirectory('%OVERLAY_PATH%', '%ZIP_PATH%')"
echo Compressed file is moved to the Desktop.

pause