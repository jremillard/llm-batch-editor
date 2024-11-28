from typing import List, Dict, Any

import logging
import time

from openai import OpenAI
from anthropic import Anthropic

from LLMRunError import LLMRunError

class LLMBot:
    """Interfaces with the LLM API."""

    def __init__(self, max_retries: int = 3, retry_delay: int = 5):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        # List of LLM models that do not support the 'role' key in messages
        self.models_without_role_key = {"o1-mini", "o1-preview"}
        # Initialize OpenAI client

        self.clientOpenAI = OpenAI()
        self.clientAnthropic = Anthropic(timeout=120.0)

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
                if ( model in ["gpt-4o-mini" ,"o1-mini","o1-preview"] ):
                    content = self.get_response_openAI(prompt, model)
                else:
                    content = self.get_response_antropic( prompt, model)
                
                logging.debug(f"Received response from LLM: {content[:50]}...")

                # Overwrite the last item as the assistant response
                if model not in self.models_without_role_key:
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

        # Ensure the prompt starts with a system message if it is not already present
        if not prompt or prompt[0].get('role') != 'system':
            if model not in self.models_without_role_key:
                prompt.insert(0, {"role": "system", "content": "You are expert software engineer from MIT."})

        completion = self.clientOpenAI.chat.completions.create(
            model=model,
            messages=prompt
        )

        content = completion.choices[0].message.content

        return content
