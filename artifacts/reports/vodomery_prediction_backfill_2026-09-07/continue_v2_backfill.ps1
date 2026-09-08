$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\tra\PycharmProjects\monitorovaci_platforma'
$python = 'C:\Users\tra\PycharmProjects\monitorovaci_platforma\.venv\Scripts\python.exe'
$log = 'artifacts\reports\vodomery_prediction_backfill_2026-09-07\continue_v2_backfill.log'
$verify = 'artifacts\reports\vodomery_prediction_backfill_2026-09-07\verify_v2_after_continue.json'
$common = @(
  'scripts\vodomery_prediction_backfill.py',
  'write',
  '--start-date', '2025-08-18',
  '--history-start-date', '2024-01-01',
  '--end-date', '2026-09-07',
  '--archive-version', '2',
  '--archive-run-id', 'vodomery-corrected-history-2026-09-07',
  '--identifikace', 'A_V3',
  '--identifikace', 'E_V4',
  '--identifikace', 'E_V5',
  '--identifikace', 'B1_V1',
  '--identifikace', 'A_V1',
  '--identifikace', 'B0_V2',
  '--identifikace', 'B_V3',
  '--identifikace', 'Bk_V1',
  '--identifikace', 'O_V1',
  '--identifikace', 'P_V2',
  '--identifikace', 'SCVK_DV',
  '--identifikace', 'SCVK_ST',
  '--indent', '0'
)
$started = Get-Date -Format o
"START $started" | Set-Content -Path $log -Encoding UTF8
& $python @common >> $log 2>&1
$writeExit = $LASTEXITCODE
"WRITE_EXIT $writeExit" >> $log
$verifyArgs = @(
  'scripts\vodomery_prediction_backfill.py',
  'verify',
  '--start-date', '2024-01-01',
  '--end-date', '2026-09-07',
  '--archive-version', '2',
  '--identifikace', 'A_V3',
  '--identifikace', 'E_V4',
  '--identifikace', 'E_V5',
  '--identifikace', 'B1_V1',
  '--identifikace', 'A_V1',
  '--identifikace', 'B0_V2',
  '--identifikace', 'B_V3',
  '--identifikace', 'Bk_V1',
  '--identifikace', 'O_V1',
  '--identifikace', 'P_V2',
  '--identifikace', 'SCVK_DV',
  '--identifikace', 'SCVK_ST',
  '--indent', '2'
)
& $python @verifyArgs > $verify 2>> $log
$verifyExit = $LASTEXITCODE
"VERIFY_EXIT $verifyExit" >> $log
$finished = Get-Date -Format o
"FINISH $finished" >> $log
exit $writeExit
