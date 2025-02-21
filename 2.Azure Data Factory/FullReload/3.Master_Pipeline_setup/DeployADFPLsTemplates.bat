@echo off
REM Connect to your Azure account
REM PowerShell -NoProfile -Command "Connect-AzAccount"


REM Check if there is an active Azure context using PowerShell
powershell.exe -NoProfile -Command "$azContext = Get-AzContext -ErrorAction SilentlyContinue; if ($azContext -eq $null) { Write-Host 'Connecting to Azure...'; Connect-AzAccount; } else { Write-Host 'You are already connected to Azure.'; }"



REM Load configuration from file (inside the 'files' folder, one step back)
if exist config.txt (
    for /f "usebackq delims=" %%a in (config.txt) do (
        set "%%a"
    )
)

REM Prompt the user for missing values
if "%SubscriptionId%"=="" (
    set /p SubscriptionId=Enter the SubscriptionId:
    echo SubscriptionId=%SubscriptionId% > config.txt
)

if "%ResourceGroupName%"=="" (
    set /p ResourceGroupName=Enter the ResourceGroupName:
    echo ResourceGroupName=%ResourceGroupName% >> config.txt
)

if "%DataFactoryName%"=="" (
    set /p DataFactoryName=Enter the DataFactoryName:
    echo DataFactoryName=%DataFactoryName% >> config.txt
)

REM Display the values
echo SubscriptionId: %SubscriptionId%
echo ResourceGroupName: %ResourceGroupName%
echo DataFactoryName: %DataFactoryName%


REM Set Azure context
echo "Set-AzContext -SubscriptionId %subscriptionId%"
PowerShell -NoProfile -Command "Set-AzContext -SubscriptionId %subscriptionId%"

REM Get current folder path
set "current_dir=%CD%"
echo Current folder path is: %current_dir%

REM Create destination folder if it doesn't exist
set "destFolder=%current_dir%\Published"
if not exist "%destFolder%" mkdir "%destFolder%"

REM Loop through JSON files in the current directory
for %%f in (*.json) do (
    if "%%~xf"==".json" (
        echo Deploying %%~nf.json
        
        REM Deploy pipeline using Azure PowerShell
        PowerShell -NoProfile -Command "Set-AzDataFactoryV2Pipeline -ResourceGroupName %resourceGroupName% -DataFactoryName %dataFactoryName% -Name '%%~nf' -File '%%~nf.json'"

        REM Check if deployment was successful
        if %errorlevel% neq 0 (
            echo Error deploying %%~nf.json >> deployment_errors.txt
        ) else (
            echo Successfully Deployed PL: %%~nf.json >> deployment_output_status.txt
            move "%%~nf.json" "%destFolder%\"
        )
        
    )
)

REM Pause to see displayed messages before closing
pause
