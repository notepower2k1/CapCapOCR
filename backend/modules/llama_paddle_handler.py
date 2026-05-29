from __future__ import annotations

from llama_cpp.llama_chat_format import Llava15ChatHandler


class PaddleOCRChatHandler(Llava15ChatHandler):
    PADDLEOCR_EOS_TOKEN = "</s>"

    CHAT_FORMAT = (
        "{%- if not add_generation_prompt is defined -%}{%- set add_generation_prompt = true -%}{%- endif -%}"
        "{%- if not eos_token is defined -%}{%- set eos_token = '" + PADDLEOCR_EOS_TOKEN + "' -%}{%- endif -%}"
        "{{- '<|begin_of_sentence|>' -}}"
        "{%- for message in messages -%}"
        "{%- if message['role'] == 'user' -%}"
        "{{- 'User: ' -}}"
        "{%- if message['content'] is string -%}"
        "{{- message['content'] -}}"
        "{%- else -%}"
        "{%- for content in message['content'] -%}"
        "{%- if content['type'] == 'image_url' and 'image_url' in content -%}"
        "{{- '<|IMAGE_START|>' -}}"
        "{%- if content.image_url is string -%}"
        "{{- content.image_url -}}"
        "{%- else -%}"
        "{{- content.image_url.url -}}"
        "{%- endif -%}"
        "{{- '<|IMAGE_END|>' -}}"
        "{%- endif -%}"
        "{%- endfor -%}"
        "{%- for content in message['content'] -%}"
        "{%- if content['type'] == 'text' -%}"
        "{{- content['text'] -}}"
        "{%- endif -%}"
        "{%- endfor -%}"
        "{%- endif -%}"
        "{{- '\\n' -}}"
        "{%- elif message['role'] == 'assistant' -%}"
        "{{- 'Assistant:\\n' -}}"
        "{%- if message['content'] is string -%}"
        "{{- message['content'] -}}"
        "{%- else -%}"
        "{%- for content in message['content'] -%}"
        "{%- if content['type'] == 'text' -%}"
        "{{- content['text'] -}}"
        "{%- endif -%}"
        "{%- endfor -%}"
        "{%- endif -%}"
        "{{- eos_token -}}"
        "{%- elif message['role'] == 'system' -%}"
        "{%- if message['content'] is string -%}"
        "{{- message['content'] + '\\n' -}}"
        "{%- else -%}"
        "{%- for content in message['content'] -%}"
        "{%- if content['type'] == 'text' -%}"
        "{{- content['text'] + '\\n' -}}"
        "{%- endif -%}"
        "{%- endfor -%}"
        "{%- endif -%}"
        "{%- endif -%}"
        "{%- endfor -%}"
        "{%- if add_generation_prompt -%}"
        "{{- 'Assistant:\\n' -}}"
        "{%- endif -%}"
    )

    def __call__(self, **kwargs):
        kwargs["stop"] = [self.PADDLEOCR_EOS_TOKEN]
        return super().__call__(**kwargs)
