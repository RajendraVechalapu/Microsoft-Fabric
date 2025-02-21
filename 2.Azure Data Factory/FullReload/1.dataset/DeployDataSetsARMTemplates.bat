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
PowerShell -NoProfile -Command "Set-AzContext -SubscriptionId %SubscriptionId%"

REM Set current folder and destination folder
set "current_dir=%CD%"
set "destFolder=%current_dir%\Published"

REM Create destination folder if it doesn't exist
if not exist "%destFolder%" mkdir "%destFolder%"

REM Loop through JSON files in the current directory
for %%f in (*.json) do (
    if "%%~xf"==".json" (
        echo Deploying dataset %%~nf.json
        
        REM Deploy dataset using Azure PowerShell
        PowerShell -NoProfile -Command "Set-AzDataFactoryV2Dataset -ResourceGroupName %ResourceGroupName% -DataFactoryName %DataFactoryName% -Name '%%~nf' -DefinitionFile '%%~nf.json'"

        REM Check if deployment was successful
        if %errorlevel% neq 0 (
            echo Error deploying %%~nf.json >> deployment_errors.txt
        ) else (
            echo Successfully Deployed DS: %%~nf.json >> deployment_output_status.txt
            move "%%~nf.json" "%destFolder%\"
        )
    )
)

REM Display completion message
echo Deployment and file move completed successfully!
pause
