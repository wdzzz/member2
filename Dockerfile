FROM python:3.11-slim

# 将应用代码安装在系统目录
WORKDIR /opt/member

RUN pip install flask --quiet

COPY server.py .
COPY public/ ./public/
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# 数据卷挂载点（数据库文件存放于此）
VOLUME [ "/app" ]

EXPOSE 5052

CMD ["./entrypoint.sh"]
