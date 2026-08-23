@echo off
rem Wrapper so the collector can be CREATED by WMI (Win32_Process.Create) rather
rem than by Start-Process. The Claude VM Service keeps its processes in a Windows
rem JOB OBJECT: on 2026-08-18 16:20:29 and again on 2026-08-19 10:26:03 that
rem service restarted and the collector died with it -- orphaned, not parented,
rem so detaching from the shell is not enough. The process has to be created
rem outside the job, and WmiPrvSE creates it, so it never joins ours.
cd /d "D:\Papers\Kalshi replication lab"
".venv\Scripts\kmt.exe" fetch pass1 --max-series 0 --panel-quote-window r2 --panel-quote-close-from 2026-05-01 --panel-quote-close-to 2026-06-30 2> "data\logs\pass1_r2_quotes_tail-2026-05..2026-06_wmi-20260819-103436.log" 1> "data\logs\pass1_r2_quotes_tail-2026-05..2026-06_wmi-20260819-103436.out.log"
