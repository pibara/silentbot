FROM python:3.9-alpine
RUN apk update && apk upgrade && apk add --no-cache nano openssl ca-certificates gettext && pip install --upgrade "pip>=19.0.2"
RUN pip install lighthive
WORKDIR /application
COPY  lookup.json  silentbot.py /application/


