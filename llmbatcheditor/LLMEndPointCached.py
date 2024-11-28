import os
import hashlib
from typing import List, Dict, Any, Tuple
from llmbatcheditor.LLMEndPoint import LLMEndPoint

class LLMEndPointCached(LLMEndPoint):
    def __init__(self, cache_dir: str, max_retries: int = 3, retry_delay: int = 5):
        super().__init__(max_retries, retry_delay)
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

    def get_response(self, prompt: List[Dict[str, str]], model: str) -> Tuple[str, bool]:
        prompt_str = str(prompt) + model
        md5_hash = hashlib.md5(prompt_str.encode('utf-8')).hexdigest()
        prompt_file = os.path.join(self.cache_dir, f"{md5_hash}.prompt.txt")
        response_file = os.path.join(self.cache_dir, f"{md5_hash}.response.txt")

        if os.path.exists(prompt_file) and os.path.exists(response_file):
            with open(response_file, 'r', encoding='utf-8') as f:
                content = f.read()
            return content
        else:
            content = super().get_response(prompt, model)
            with open(prompt_file, 'w', encoding='utf-8') as f:
                f.write(prompt_str)
            with open(response_file, 'w', encoding='utf-8') as f:
                f.write(content)
            return content
