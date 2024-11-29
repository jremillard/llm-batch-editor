from typing import List, Dict, Any

import logging
from pathlib import Path
import toml
from llmbatcheditor.LLMRunError import LLMRunError
import llmbatcheditor.LLMEndPoint

# Constants for built-in macros
BUILT_IN_MACROS = {"filename", "output", "filelist", "filename_base"}


class InstructionParser:
    """Parses and validates the instruction TOML file."""

    def __init__(self, instruction_path: Path):
        self.instruction_path = instruction_path
        self.instruction_dir = instruction_path.parent
        self.data = self.load_toml()
        self.validate_unique_command_ids()
        self.validate_macros()
        self.validate_commands()

    def load_toml(self) -> Dict[str, Any]:
        try:
            with open(self.instruction_path, 'r') as f:
                data = toml.load(f)
            logging.debug(f"Successfully loaded TOML file: {self.instruction_path}")
            return data
        except Exception as e:
            raise LLMRunError(f"Failed to load TOML file: {e}")

    def validate_unique_command_ids(self):
        commands = self.data.get("commands", [])
        seen_ids = set()
        for cmd in commands:
            cmd_id = cmd.get("id")
            if not cmd_id:
                raise LLMRunError("A command is missing the required 'id' field.")
            if cmd_id in seen_ids:
                raise LLMRunError(f"Duplicate command id found: '{cmd_id}'. Each command must have a unique 'id'.")
            seen_ids.add(cmd_id)
        logging.debug("All command IDs are unique.")

    def validate_macros(self):
        shared_prompts = self.data.get("shared_prompts", {})
        for macro_name in shared_prompts:
            if macro_name in BUILT_IN_MACROS:
                raise LLMRunError(f"Macro name conflict: '{macro_name}' is a reserved built-in macro name.")
        logging.debug("All custom macros are validated and no conflicts found.")

    def validate_commands(self):
        commands = self.data.get("commands", [])
        defaults = self.data.get("defaults", {})
        supported_models = llmbatcheditor.LLMEndPoint.LLMEndPoint.get_supported_models()
        for index, cmd in enumerate(commands, start=1):
            cmd_id = cmd.get("id", f"<command at position {index}>")
            cmd_type = cmd.get("type")
            if not cmd_type:
                raise LLMRunError(f"Command '{cmd_id}' is missing the required 'type' field.")

            # Check for required general fields
            for field in ["id", "type", "target_files", "instruction"]:
                if field not in cmd:
                    raise LLMRunError(f"Command '{cmd_id}' is missing the required '{field}' field.")

            # Specific validations per command type
            if cmd_type == "llm_create":
                if "context" not in cmd:
                    raise LLMRunError(f"Command '{cmd_id}' of type 'llm_create' must include 'context'.")
            elif cmd_type == "llm_edit":
                # 'context' is optional but recommended
                pass
            elif cmd_type == "llm_feedback_edit":
                if "test_commands" not in cmd:
                    raise LLMRunError(f"Command '{cmd_id}' of type 'llm_feedback_edit' must include 'test_commands'.")
                if "max_retries" not in cmd:
                    raise LLMRunError(f"Command '{cmd_id}' of type 'llm_feedback_edit' must include 'max_retries'.")
                instruction = cmd.get("instruction", "")
            else:
                raise LLMRunError(f"Unsupported command type: '{cmd_type}' in command '{cmd_id}'.")

            # Validate model if specified
            model = cmd.get("model", defaults.get("model"))
            if model and model not in supported_models:
                raise LLMRunError(f"Unsupported model '{model}' specified in command '{cmd_id}'. Supported models: {supported_models}")

            # Validate other fields
            if not isinstance(cmd.get("target_files"), list) or not all(isinstance(f, str) for f in cmd.get("target_files")):
                raise LLMRunError(f"'target_files' in command '{cmd_id}' must be an array of strings.")
            if "context" in cmd:
                if not isinstance(cmd.get("context"), list) or not all(isinstance(c, str) for c in cmd.get("context")):
                    raise LLMRunError(f"'context' in command '{cmd_id}' must be an array of strings.")
            if cmd_type == "llm_feedback_edit":
                if not isinstance(cmd.get("test_commands"), list) or not all(isinstance(tc, str) for tc in cmd.get("test_commands")):
                    raise LLMRunError(f"'test_commands' in command '{cmd_id}' must be an array of strings.")
                if not isinstance(cmd.get("max_retries"), int) or cmd.get("max_retries") <= 0:
                    raise LLMRunError(f"'max_retries' in command '{cmd_id}' must be a positive integer.")

        logging.debug("All commands are validated successfully.")

    def get_data(self) -> Dict[str, Any]:
        return self.data

