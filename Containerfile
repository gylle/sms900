FROM python:3
WORKDIR /usr/src/app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

RUN cd sms900/tests && python3 -m unittest

EXPOSE 9999

CMD ["python", "./bot.py"]
