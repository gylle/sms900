FROM docker.io/library/python:3-alpine
WORKDIR /usr/src/app
COPY requirements.txt ./
RUN apk add --no-cache git \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN cd sms900/tests && python3 -m unittest

EXPOSE 9999
CMD ["python", "./bot.py"]
