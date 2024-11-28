from typing import List, Dict, Any
import re

class MacroResolver:
    """Resolves macros within instructions."""

    def __init__(self, shared_prompts: Dict[str, str]):
        self.shared_prompts = shared_prompts

    def resolve_shared_prompts(self, text: str) -> str:
        """
        Replace shared prompts in the instruction text.
        """
        def replace_shared_prompt(match):
            macro = match.group(1)
            if macro in self.shared_prompts:
                return self.shared_prompts[macro]
            return match.group(0)  # Leave it unchanged if not a shared prompt

        return re.sub(r"\{\{(\w+)\}\}", replace_shared_prompt, text.strip())

    def resolve_placeholders(self, text: str, placeholders: Dict[str, str]) -> str:
        """
        Replace built-in macros in the instruction text.
        """
        for key, value in placeholders.items():
            text = text.replace(f"{{{{{key}}}}}", value.strip())
        return text

    def resolve(self, text: str, placeholders: Dict[str, str]) -> str:
        """
        Resolve shared prompts and built-in macros in the given text.
        """
        text = self.resolve_shared_prompts(text)
        text = self.resolve_placeholders(text, placeholders)
        return text
