import logging
import openai

class OpenAI():
    def __init__(self, api_key, config_engine, config_prompt):
        openai.api_key = api_key

        self.config_engine = config_engine
        self.config_prompt = config_prompt

    def set_prompt(self, new_config_prompt):
        self.config_prompt = new_config_prompt

    def generate_response(self, channel, my_nickname, history):
        prompt_to_complete = self.generate_prompt(channel, my_nickname, history)
        return self.complete_prompt(prompt_to_complete)

    def generate_prompt(self, channel, my_nickname, history):
        prompt = (
            "You're on an IRC channel called {channel} and your nickname is {nick}."
            + self.config_prompt
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
