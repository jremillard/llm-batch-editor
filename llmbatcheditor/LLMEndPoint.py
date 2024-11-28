from typing import List, Dict, Any

import logging
import time

from openai import OpenAI
from anthropic import Anthropic

from llmbatcheditor.LLMRunError import LLMRunError


class LLMEndPoint:
    """Interfaces with the LLM API."""

    openai_models = {"o1-mini", "o1-preview", "gpt-4o", "gpt-4o-mini"}
    anthropic_models = {"claude-3-5-sonnet-latest", "claude-3-5-haiku-latest"}

    # List of LLM models that do not support the 'role' key in messages, and should not include it in the prompt
    # only OpenAI reasining models.
    models_without_role_key = {"o1-mini", "o1-preview"}

    def __init__(self, max_retries: int = 3, retry_delay: int = 5):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Initialize clients as None for lazy instantiation
        self.clientOpenAI = None
        self.clientAnthropic = None

    @classmethod
    def get_supported_models(cls):
        return cls.openai_models.union(cls.anthropic_models)

    def get_response(self, prompt: List[Dict[str, str]], model: str) -> str:
        """
        Sends a prompt to the LLM and returns the response.
        If conversation history is provided, includes it for context-aware responses.
        Implements retry logic on failure.

        :param prompt: A list of dictionaries containing conversation messages with required keys "role" and "content".
                       Valid values for "role" are "system", "user", or "assistant".
        :param model: The model to use for the LLM API.
        :return: The response from the LLM.
        """

        # Ensure all dictionaries in prompt contain only 'role' and 'content' keys
        for message in prompt:
            if set(message.keys()) - {"role", "content"}:
                raise ValueError("Each message in the prompt must only contain 'role' and 'content' keys.")

        # Prepare the prompt for sending: raise an error if the last item has the role 'assistant'
        if prompt[-1].get('role') == 'assistant':
            raise ValueError("The last item in the prompt cannot have the role 'assistant' before sending to the LLM.")

        for attempt in range(1, self.max_retries + 1):
            try:
                logging.debug(f"Sending prompt to LLM (Attempt {attempt}): {prompt[-1].get('content', '')[:50]}...")

                content = ""
                if model in LLMEndPoint.openai_models:
                    content = self.get_response_openAI(prompt, model)
                elif model in LLMEndPoint.anthropic_models:
                    content = self.get_response_antropic(prompt, model)
                else:
                    raise ValueError(f"Unsupported model: {model}")

                logging.debug(f"Received response from LLM: {content[:50]}...")

                # Overwrite the last item as the assistant response
                if model not in LLMEndPoint.models_without_role_key:
                    prompt[-1] = {"role": "assistant", "content": content}
                else:
                    prompt[-1] = {"content": content}

                return content

            except Exception as e:
                logging.warning(f"LLM API call failed on attempt {attempt}: {e}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                else:
                    raise LLMRunError(f"LLM API call failed after {self.max_retries} attempts: {e}")

    def get_response_antropic(self, prompt: List[Dict[str, str]], model: str) -> str:
        if self.clientAnthropic is None:
            self.clientAnthropic = Anthropic(timeout=120.0)
        response = self.clientAnthropic.messages.create(
            max_tokens=8000,
            model=model,
            messages=prompt
        )

        content = ""
        if hasattr(response, "content"):
            content = "".join(
                block.text for block in response.content if hasattr(block, "text")
            )
        return content

    def get_response_openAI(self, prompt: List[Dict[str, str]], model: str) -> str:
        if self.clientOpenAI is None:
            self.clientOpenAI = OpenAI()
        # Ensure the prompt starts with a system message if it is not already present
        if not prompt or prompt[0].get('role') != 'system':
            if model not in LLMEndPoint.models_without_role_key:
                prompt.insert(0, {"role": "system", "content": "You are expert software engineer from MIT."})

        completion = self.clientOpenAI.chat.completions.create(
            model=model,
            messages=prompt
        )

        content = completion.choices[0].message.content

        return content
