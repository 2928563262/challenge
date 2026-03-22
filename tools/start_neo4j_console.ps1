param([string]$NeoHome)
powershell -ExecutionPolicy Bypass -File (Join-Path $NeoHome 'bin\neo4j.ps1') console --verbose
