import logging
import openai

class OpenAI():
    def __init__(self, config):
        openai.api_key = config['openai_api_key']

        self.config_engine = config['openai_engine'],
        self.config_prompt = config['openai_prompt'] if 'openai_prompt' in config else ''
        self.config_use_chat = config['openai_use_chat']
        self.config_chat_model = config['openai_chat_model']

        self.override_prompt = None

    def set_prompt(self, prompt):
        self.override_prompt = prompt

    def generate_response(self, channel, my_nickname, history):
        prompt = self.generate_prompt(channel, my_nickname, history)

        if self.config_use_chat:
            return self.complete_prompt_chat(prompt)

        return self.complete_prompt(prompt)

    def generate_prompt(self, channel, my_nickname, history):
        chat_instructions = (
            "Your repsonses usually fit on a line, but you can use multiple lines when for example generating code. "
            + "You never include \"<{nick}>\" in your completion. "
        )

        prompt = (
            "You're on an IRC channel called {channel} and your nickname is {nick}. "
            + "You have the ability to send SMS by writing '|SMS:recipient:message|', including the '|'. "
            + "If you want to send SMS to multiple people, you need to write the command multiple times. "
            + "You only send SMS or even talk about SMS when someone explicitly asks you to. "
            + (chat_instructions if self.config_use_chat else "")
            + (self.override_prompt if self.override_prompt else self.config_prompt)
        ).format(channel=channel, nick=my_nickname).strip()

        prompt += "\n\n"

        for h in history:
            if h['channel'] != channel:
                continue

            prompt += "<%s> %s\n" % (h['nickname'], h['msg'])

        prompt += "<%s>" % my_nickname

        return prompt

    def complete_prompt(self, prompt):
        try:
            completion = openai.Completion.create(
                engine=self.config_engine,
                prompt=prompt,
                stop=['<'],
                temperature=0.7,
                max_tokens=256,
            )

            return completion.choices[0].text.strip()
        except Exception as err:
            logging.info("Failed to create completion: %s", err)
            return None

    def complete_prompt_chat(self, prompt):
        try:
            completion = openai.ChatCompletion.create(
                model=self.config_chat_model,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            return completion.choices[0].message.content.strip()
        except Exception as err:
            logging.info("Failed to create completion: %s", err)
            return None
