FROM python:3.11.9-slim

WORKDIR /app

RUN python -m pip install -r requirements.txt

COPY . .

EXPOSE 8000

CMD uvicorn 'server:app' --host=0.0.0.0 --port=8000
