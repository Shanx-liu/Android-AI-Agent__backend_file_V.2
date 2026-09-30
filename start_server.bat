@echo off

echo 正在啟動 ngrok...
start "ngrok Tunnel" cmd /k "ngrok http --url=unannealed-controllingly-sarai.ngrok-free.dev 8002"

echo 服務已在獨立視窗啟動完成！