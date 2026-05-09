#!/bin/sh
# 首次启动时，将应用文件复制到挂载的数据卷
if [ ! -f /app/server.py ]; then
    cp /opt/member/server.py /app/
    cp -r /opt/member/public /app/
fi
exec python /app/server.py
