# sms900

Basic SMS <-> IRC gateway. Uses twilio to send and receive SMS.

Create a config.json before running bot.py; see config.json.example.

## Something something containers

> podman build . -t sms900
>
> touch sms900.db
>
> podman run --mount type=bind,src=/srv/sms900,dst=/srv/sms900 \
>     --mount type=bind,src=config.json,dst=/usr/src/app/config.json,readonly \
>     --mount type=bind,src=sms900.db,dst=/usr/src/app/sms900.db \
>     --detach sms900
