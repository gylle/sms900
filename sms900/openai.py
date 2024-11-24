from datetime import datetime
import logging
import openai
import re

class OpenAI():
    def __init__(self, config):
        openai.api_key = config['openai_api_key']

        self.config_engine = config['openai_engine'],
        self.config_prompt = config['openai_prompt'] if 'openai_prompt' in config else ''
        self.config_use_chat = config['openai_use_chat']
        self.config_chat_model = config['openai_chat_model']
        self.max_line_length = 430

        self.override_prompt = None
        self.override_chat_model = None

    def set_prompt(self, prompt):
        self.override_prompt = prompt

    def set_model(self, model):
        self.override_chat_model = model

    def generate_response(self, channel, my_nickname, history):
        prompt = self.generate_prompt(channel, my_nickname, history)

        try:
            if self.config_use_chat:
                completion = self.complete_prompt_chat(prompt)
            else:
                completion = self.complete_prompt(prompt)

            return self.strip_imaginary_response(
                self.splitlong(completion)
            )
        except Exception as err:
            logging.info("Failed to create completion: %s", err)
            return None

    def generate_prompt(self, channel, my_nickname, history):
        chat_instructions = (
            "Your repsonses usually fit on a line, but you can use multiple lines when for example generating code. "
            + "You never include \"<{nick}>\" in your completion. "
        )

        prompt = (
            "You're on an IRC channel called {channel} and your nickname is {nick}. "
            + "You have the ability to send SMS by writing '|SMS/recipient/message|', including the '|' and '/'. "
            + "If you want to send SMS to multiple people, you need to write the command multiple times. "
            + "You can also remind yourself to do things in the future, by writing '|REMIND/relative-or-absolute-time/message|'. "
            + "In reminders, include all necessary information for you to act on them (e.g. who to remind, and so on). "
            + "Assume that no other context will be available. "
            + "Commands cannot be nested; for example you cannot include an SMS command inside a REMINDER command. "
            + "You only send/set or even talk about SMS/reminders when someone explicitly asks you to. "
            + (chat_instructions if self.config_use_chat else "")
            + (self.override_prompt if self.override_prompt else self.config_prompt)
        ).format(channel=channel, nick=my_nickname).strip()

        prompt += "\n\n"

        for h in history:
            if h['channel'] != channel:
                continue

            prompt += self.format_event(h) + "\n"

        prompt += self.format_event({
            "type": "irc",
            "timestamp": datetime.now().astimezone(),
            "nickname": my_nickname,
            "msg": "",
        })

        return prompt

    def format_event(self, e):
        time = e['timestamp'].strftime("%Y-%m-%d %H:%M:%S %Z")

        match e['type']:
            case 'sms':
                return f"[{time}] [SMS from {e['nickname']}] {e['msg']}"
            case 'reminder':
                return f"[{time}] [REMINDER TRIGGERED] {e['msg']}"

        return f"[{time}] <{e['nickname']}> {e['msg']}"

    def complete_prompt(self, prompt):
        completion = openai.Completion.create(
            engine=self.config_engine,
            prompt=prompt,
            stop=['<'],
            temperature=0.7,
            max_tokens=256,
        )

        return completion.choices[0].text.strip()

    def complete_prompt_chat(self, prompt):
        model = self.override_chat_model if self.override_chat_model else self.config_chat_model
        completion = openai.ChatCompletion.create(
            model=model,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )

        return completion.choices[0].message.content.strip()

    def strip_imaginary_response(self, text):
        m = re.match(r'(.+)\n<[-_a-zA-Z0-9]+>', text, re.M|re.S)
        if m:
            return m[1]

        return text

    def splitlong(self, text):
        space = 32
        newline = 10

        last_newline = 0
        last_space = None

        text = text.encode('UTF-8', 'ignore')
        new_text = b""

        for i in range(0, len(text)):
            if text[i] == newline:
                new_text += text[last_newline:i+1]
                last_newline = i+1
                last_space = None
                continue

            if text[i] == space:
                last_space = i

            if i - last_newline < self.max_line_length:
                continue

            splitat = i if not last_space else last_space
            while splitat > last_newline and (text[splitat] & 0xc0) == 0x80:
                splitat -= 1

            new_text += text[last_newline:splitat] + b"\n"
            last_newline = splitat + (1 if last_space else 0)
            last_space = None

        new_text += text[last_newline:]

        return new_text.decode('UTF-8', 'ignore')
