C:\rclone\rclone.exe sync --http-url https://mztrading-parquetfiles.deno.dev/files :http: ./options-data --progress  >> C:\ws\logs\log.log 2>&1
python job-consolidate.py  >> C:\ws\logs\log.log 2>&1