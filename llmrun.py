from typing import List, Dict, Any
import argparse
import os
import sys
import shutil
from pathlib import Path
import logging
import subprocess
import time
import re
import traceback
import concurrent.futures
import toml
import json
from openai import OpenAI
from anthropic import Anthropic

# Constants for built-in macros
BUILT_IN_MACROS = {"filename", "output", "filelist", "filename_base"}

# List of binary file extensions for 'filelist' macro
BINARY_EXTENSIONS = {
    ".exe",
    ".dll",
    ".bin",
    ".dat",
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".iso",
    ".tar",
    ".gz",
    ".zip",
    ".7z",
    ".rar",
    ".so",
    ".dylib",
    ".class",
    ".jar",
    ".egg"
    # Add more as needed
}


class LLMRunError(Exception):
    """Custom exception for llmrun errors."""
    pass


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
        supported_models = {"o1-mini", "o1-preview","gpt-4o","gpt-4o-mini","claude-3-5-sonnet-latest","claude-3-5-haiku-latest"}  # Extend as needed
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
                if "{{output}}" not in instruction:
                    raise LLMRunError(f"Command '{cmd_id}' of type 'llm_feedback_edit' must include '{{{{output}}}}' in 'instruction'.")
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


class ContextManager:
    """Manages context gathering based on file patterns."""

    def __init__(self, target_directory: Path):
        self.target_directory = target_directory

    def generate_filelist(self) -> str:
        """
        Generates a list of files in the target directory with their sizes.
        Excludes 'log' and '__pycache__' directories.
        For binary files, includes a snippet of their content.
        """
        filelist = ["LIST OF FILE"]
        for root, dirs, files in os.walk(self.target_directory):
            # Exclude 'log' and '__pycache__' directories
            dirs[:] = [d for d in dirs if d not in ("log", "__pycache__")]
            for file in files:
                file_path = Path(root) / file
                rel_path = file_path.relative_to(self.target_directory)
                size = file_path.stat().st_size
                entry = f"{rel_path} - {size} bytes"
                filelist.append(entry)
        return "\n".join(filelist)

    def gather_context(self, patterns: List[str]) -> List[str]:
        """
        Gathers context items based on glob patterns.
        """
        context_items = []
        for pattern in patterns:
            # Handle special tokens like {{filelist}}
            if pattern == "{{filelist}}":
                context_items.append(self.generate_filelist())
                continue
            # Resolve glob patterns relative to target directory
            matched_files = list(self.target_directory.glob(pattern))
            for file_path in matched_files:
                if file_path.is_file():                        
                    context_items.append('-'*80)
                    context_items.append(f"File: {os.path.relpath(file_path, self.target_directory)}")
                    context_items.append('-'*80)

                    if file_path.suffix.lower() in BINARY_EXTENSIONS:
                        try:
                            with open(file_path, 'rb') as f:
                                while True:
                                    chunk = f.read(40)
                                    if not chunk:
                                        break

                                    # Generate the ASCII part (dots for non-printable characters)
                                    ascii_part = ''.join(chr(byte) if 32 <= byte <= 126 else '.' for byte in chunk)

                                    # Generate the hex part
                                    hex_part = ' '.join(f"{byte:02x}" for byte in chunk)

                                    # Combine ASCII and hex parts
                                    line = f"{ascii_part:<40} {hex_part}"
                                    context_items.append( line)
                        except Exception as e:
                            entry += f"\n  [Error reading binary file: {e}]"
                    else:
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                            context_items.append(content)
                        except Exception:
                            # If binary or unreadable, skip or handle accordingly
                            context_items.append(f"[Binary or unreadable file: {file_path}]")
        return context_items


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


class LoggerManager:
    """Manages logging for the application."""

    def __init__(self, log_dir: Path, debug: bool = False):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.setup_root_logger(debug=debug)

    def setup_root_logger(self, debug: bool):
        level = logging.DEBUG if debug else logging.INFO
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.StreamHandler(sys.stdout)
            ]
        )

    def setup_command_logger(self, command_id: str) -> logging.Logger:
        """
        Sets up a logger for a specific command, writing to <command_id>.log.
        """
        logger = logging.getLogger(command_id)
        logger.setLevel(logging.DEBUG)

        # Remove existing handlers to avoid duplicate logs
        if logger.hasHandlers():
            logger.handlers.clear()

        # Create file handler
        log_file = self.log_dir / f"{command_id}.log"
        fh = logging.FileHandler(log_file, mode='w', encoding='utf-8')
        fh.setLevel(logging.DEBUG)

        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        return logger

    def setup_file_loggers(self, command_id: str, file_name: str) -> Dict[str, logging.Logger]:
        """
        Sets up loggers for LLM prompt and output for a specific file.
        Returns a dictionary with 'prompt' and 'output' loggers.
        """
        prompt_logger = logging.getLogger(f"{command_id}.{file_name}.llm-prompt")
        output_logger = logging.getLogger(f"{command_id}.{file_name}.llm-output")

        # Remove existing handlers
        if prompt_logger.hasHandlers():
            prompt_logger.handlers.clear()
        if output_logger.hasHandlers():
            output_logger.handlers.clear()

        # Prompt logger
        prompt_file = self.log_dir / f"{command_id}.{file_name}.llm-prompt.txt"
        ph = logging.FileHandler(prompt_file, mode='w', encoding='utf-8')
        ph.setLevel(logging.DEBUG)
        ph.setFormatter(logging.Formatter("%(message)s"))
        prompt_logger.addHandler(ph)
        prompt_logger.propagate = False

        # Output logger
        output_file = self.log_dir / f"{command_id}.{file_name}.llm-output.txt"
        oh = logging.FileHandler(output_file, mode='w', encoding='utf-8')
        oh.setLevel(logging.DEBUG)
        oh.setFormatter(logging.Formatter("%(message)s"))
        output_logger.addHandler(oh)
        output_logger.propagate = False

        return {"prompt": prompt_logger, "output": output_logger}


class CommandExecutor:
    """Executes commands as per the instruction file."""

    def __init__(self, instruction_data: Dict[str, Any], instruction_dir: Path, target_dir: Path,
                 logger_manager: LoggerManager, llm_bot: LLMBot, macro_resolver: MacroResolver,
                 context_manager: ContextManager, selected_commands: List[Dict[str, Any]],
                 max_workers: int = 5):
        self.commands = selected_commands
        self.defaults = instruction_data.get("defaults", {})
        self.shared_prompts = instruction_data.get("shared_prompts", {})
        self.instruction_dir = instruction_dir
        self.target_dir = target_dir
        self.logger_manager = logger_manager
        self.llm_bot = llm_bot
        self.macro_resolver = macro_resolver
        self.context_manager = context_manager
        self.max_workers = max_workers  # Maximum number of threads for parallel processing

    def execute_all(self):
        for command in self.commands:
            cmd_id = command.get("id")
            cmd_type = command.get("type")
            logger = self.logger_manager.setup_command_logger(cmd_id)
            logger.info(f"Starting command '{cmd_id}' of type '{cmd_type}'.")

            try:
                if cmd_type == "llm_create":
                    self.execute_llm_create(command, logger)
                elif cmd_type == "llm_edit":
                    self.execute_llm_edit(command, logger)
                elif cmd_type == "llm_feedback_edit":
                    self.execute_llm_feedback_edit(command, logger)
                else:
                    raise LLMRunError(f"Unsupported command type '{cmd_type}' in command '{cmd_id}'.")

                logger.info(f"Command '{cmd_id}' completed successfully.")
                print(f"Command '{cmd_id}': OK")
            except Exception as e:
                logger.error(f"Command '{cmd_id}' failed with error: {e}\n{traceback.format_exc()}")
                print(f"Command '{cmd_id}': ERROR")
                # Depending on specification, decide whether to continue or halt
                # Here, continue to next command
                continue

    def execute_llm_create(self, command: Dict[str, Any], logger: logging.Logger):
        target_files = command.get("target_files", [])
        instruction = command.get("instruction", "")
        context_patterns = command.get("context", [])
        model = command.get("model", self.defaults.get("model", "gpt-4"))

        # Use ThreadPoolExecutor for parallel processing
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {
                executor.submit(self.process_create_file, file_name, instruction, context_patterns, model, logger): file_name
                for file_name in target_files
            }
            for future in concurrent.futures.as_completed(future_to_file):
                file_name = future_to_file[future]
                try:
                    future.result()
                    logger.info(f"File '{file_name}' created successfully.")
                except Exception as e:
                    logger.error(f"Error creating file '{file_name}': {e}")

    def process_create_file(self, file_name: str, instruction: str, context_patterns: List[str], model: str, logger: logging.Logger):
        logger.info(f"Creating file '{file_name}'.")
        placeholders = {
            "filename": file_name,
            "filename_base": os.path.splitext(file_name)[0],
            "output": "",
            "filelist": self.context_manager.generate_filelist()
        }
        resolved_instruction = self.macro_resolver.resolve(instruction, placeholders)

        # Gather context
        context_items = self.context_manager.gather_context(context_patterns)
        # Combine context into a single string or structure as needed
        full_prompt = resolved_instruction + "\n" + "\n".join(context_items)

        # Log prompt
        file_loggers = self.logger_manager.setup_file_loggers(logger.name, file_name)
        file_loggers["prompt"].info(full_prompt)

        # Get LLM response
        llm_response = self.llm_bot.get_response([{"role": "user", "content": full_prompt}], model=model)

        # Log response
        file_loggers["output"].info(llm_response)

        # Process LLM output
        content_to_write = None
        if file_name.endswith('.md'):
            # If the file is a markdown file, assume the LLM response is the file content
            content_to_write = llm_response.strip()
        else:
            # For other file types, use regex to extract the longest code block
            code_blocks = re.findall(r"```[a-zA-Z0-9\+]*\n(.*?)```", llm_response, re.DOTALL)
            if code_blocks:
                content_to_write = max(code_blocks, key=len).strip()
 
        # Write to target file
        target_file_path = self.target_dir / file_name
        with open(target_file_path, 'w', encoding='utf-8') as f:
            f.write(content_to_write)

    def execute_llm_edit(self, command: Dict[str, Any], logger: logging.Logger):
        target_files = command.get("target_files", [])
        instruction = command.get("instruction", "")
        context_patterns = command.get("context", [])
        model = command.get("model", self.defaults.get("model", "gpt-4"))

        # Use ThreadPoolExecutor for parallel processing
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {
                executor.submit(self.process_edit_file, file_name, instruction, context_patterns, model, logger): file_name
                for file_name in target_files
            }
            for future in concurrent.futures.as_completed(future_to_file):
                file_name = future_to_file[future]
                try:
                    future.result()
                    logger.info(f"File '{file_name}' edited successfully.")
                except Exception as e:
                    logger.error(f"Error editing file '{file_name}': {e}")

    def process_edit_file(self, file_name: str, instruction: str, context_patterns: List[str], model: str, logger: logging.Logger):
        logger.info(f"Editing file '{file_name}'.")
        target_file_path = self.target_dir / file_name
        if not target_file_path.exists():
            logger.error(f"File '{file_name}' does not exist. Skipping.")
            return

        try:
            with open(target_file_path, 'r', encoding='utf-8') as f:
                
                target_file_content = f.read()
        except Exception as e:
            logger.error(f"Failed to read file '{file_name}': {e}")
            return

        placeholders = {
            "filename": file_name,
            "filename_base": os.path.splitext(file_name)[0],
            "output": "",
            "filelist": self.context_manager.generate_filelist()
        }
        resolved_instruction = self.macro_resolver.resolve(instruction, placeholders)

        # Gather context, including the current file content
        context_items = []

        context_items.append('-'*80) 
        context_items.append(f"File: {file_name}")
        context_items.append('-'*80) 
        context_items.append(target_file_content)
        context_items.extend( self.context_manager.gather_context(context_patterns))

        full_prompt = resolved_instruction + "\n" + "\n".join(context_items)

        # Log prompt
        file_loggers = self.logger_manager.setup_file_loggers(logger.name, file_name)
        file_loggers["prompt"].info(full_prompt)

        # Get LLM response
        llm_response = self.llm_bot.get_response([{"role": "user", "content": full_prompt}], model=model)

        # Log response
        file_loggers["output"].info(llm_response)

        content_to_write = None
        if file_name.endswith('.md'):
            # If the file is a markdown file, assume the LLM response is the file content
            content_to_write = llm_response.strip()
        else:
            # For other file types, use regex to extract the longest code block
            code_blocks = re.findall(r"```[a-zA-Z0-9\+]*\n(.*?)```", llm_response, re.DOTALL)
            if code_blocks:
                content_to_write = max(code_blocks, key=len).strip()
 
        # Write updated content to the file
        with open(target_file_path, 'w', encoding='utf-8') as f:
            f.write(content_to_write)

    def execute_llm_feedback_edit(self, command: Dict[str, Any], logger: logging.Logger):
        target_files = command.get("target_files", [])
        instruction = command.get("instruction", "")
        test_commands = command.get("test_commands", [])
        max_retries = command.get("max_retries", 3)
        context_patterns = command.get("context", [])
        model = command.get("model", self.defaults.get("model", "gpt-4"))

        # Use ThreadPoolExecutor for parallel processing
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {
                executor.submit(self.process_feedback_edit_file, file_name, instruction, test_commands, max_retries, context_patterns, model, logger): file_name
                for file_name in target_files
            }
            for future in concurrent.futures.as_completed(future_to_file):
                file_name = future_to_file[future]
                try:
                    future.result()
                    logger.info(f"Feedback-editing completed successfully for '{file_name}'.")
                except Exception as e:
                    logger.error(f"Feedback-editing failed for '{file_name}': {e}")

    def process_feedback_edit_file(self, file_name: str, instruction: str, test_commands: List[str], max_retries: int,
                                   context_patterns: List[str], model: str, logger: logging.Logger):
        logger.info(f"Feedback-editing file '{file_name}'.")
        target_file_path = self.target_dir / file_name
        if not target_file_path.exists():
            logger.error(f"File '{file_name}' does not exist. Skipping.")
            return

        retry_count = 0
        success = False

        while retry_count < max_retries and not success:
            try:
                # Run test commands
                combined_output = ""

                all_success = True
                for cmd in test_commands:
                    cmd_resolved = cmd.replace("{{filename}}", str(file_name))
                    logger.info(f"Running test command: {cmd_resolved}")
                    result = subprocess.run(cmd_resolved, shell=True, capture_output=True, text=True,cwd=self.target_dir)
                    combined_output += f"$ {cmd_resolved}\nReturn Code: {result.returncode}\nStdout:\n{result.stdout}\nStderr:\n{result.stderr}\n"
                    if result.returncode != 0:
                        all_success = False

                if all_success:
                    logger.info(f"Test commands succeeded for '{file_name}'.")

                retry_count += 1

                placeholders = {
                    "filename": file_name,
                    "filename_base": os.path.splitext(file_name)[0],
                    "output": combined_output,
                    "filelist": self.context_manager.generate_filelist()
                }
                resolved_instruction = self.macro_resolver.resolve(instruction, placeholders)

                # Gather context, including the current file content
                try:
                    with open(target_file_path, 'r', encoding='utf-8') as f:
                        current_content = f.read()
                except Exception as e:
                    logger.error(f"Failed to read file '{file_name}' during feedback-edit: {e}")
                    break

                context_items = []
                context_items.append('-'*80) 
                context_items.append(f"File: {file_name}")
                context_items.append('-'*80) 
                context_items.append(current_content)
                context_items.extend( self.context_manager.gather_context(context_patterns))

                full_prompt = resolved_instruction + "\n" + "\n".join(context_items)

                # Log prompt
                file_loggers = self.logger_manager.setup_file_loggers(logger.name + f".{retry_count}", file_name)
                file_loggers["prompt"].info(full_prompt)

                # Get LLM response
                llm_response = self.llm_bot.get_response([{"role": "user", "content": full_prompt}], model=model)

                # Log response
                file_loggers["output"].info(llm_response)

                content_to_write = None
                if file_name.endswith('.md'):
                    # If the file is a markdown file, assume the LLM response is the file content
                    content_to_write = llm_response.strip()
                else:
                    # For other file types, use regex to extract the longest code block
                    code_blocks = re.findall(r"```[a-zA-Z0-9\+]*\n(.*?)```", llm_response, re.DOTALL)
                    if code_blocks:
                        content_to_write = max(code_blocks, key=len).strip()
        
                # Write updated content to the file
                if ( content_to_write is not None):
                    with open(target_file_path, 'w', encoding='utf-8') as f:
                        f.write(content_to_write)
                else:
                    success = True
            except Exception as e:
                logger.error(f"Error during feedback-editing of '{file_name}': {e}")
                break

        if success:
            logger.info(f"Feedback-editing completed successfully for '{file_name}'.")
        else:
            logger.error(f"Feedback-editing failed for '{file_name}' after {max_retries} attempts.")


def parse_command_ids(command_ids: List[str], commands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Parses command IDs from the command line arguments.

    Accepts exact matches of command 'id's, ranges using '-', and '*' to run all commands starting from a point.

    - Exact command ID: e.g., 'cmd1' selects only 'cmd1'.
    - Range of command IDs: e.g., 'cmd1-cmd3' selects 'cmd1', 'cmd2', and 'cmd3'. The syntax 'cmd1 - cmd3' is not supported.
    - Wildcard '*': selects all commands.
    - Prefix wildcard: e.g., 'cmd2*' selects 'cmd2' and all subsequent commands.

    :param command_ids: List of command ID strings from command line.
    :param commands: List of command dictionaries from the instruction file. Each dictionary must have a unique 'id' key.
    :return: List of command dictionaries that match the provided IDs.
    :raises ValueError: If any provided command ID is invalid or if a range is improperly specified.
    """
    # Ensure all command IDs are unique to prevent unexpected behavior
    seen_ids = set()
    for cmd in commands:
        cmd_id = cmd.get('id')
        if cmd_id in seen_ids:
            raise ValueError(f"Duplicate command ID found in commands list: '{cmd_id}'. Command IDs must be unique.")
        seen_ids.add(cmd_id)

    # Create a lookup dictionary for quick access to commands by their ID
    command_lookup = {cmd['id']: cmd for cmd in commands}
    command_keys = list(command_lookup.keys())  # Preserves the order of commands
    selected_commands = []
    selected_ids = set()  # To avoid duplicates

    for cid in command_ids:
        cid = cid.strip()  # Remove any leading/trailing whitespace
        if '-' in cid and not cid.startswith('-') and not cid.endswith('-'):
            # Handle ranges, e.g., 'cmd1-cmd3' or 'cmd1 - cmd3'
            parts = cid.split('-', 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid range format: '{cid}'. Expected format 'start_id-end_id'.")
            start_id, end_id = [part.strip() for part in parts]

            # Check if both start_id and end_id exist
            if start_id not in command_lookup and end_id not in command_lookup:
                raise ValueError(f"Invalid range: both '{start_id}' and '{end_id}' are not valid command IDs.")
            if start_id not in command_lookup:
                raise ValueError(f"Invalid range: start ID '{start_id}' does not exist.")
            if end_id not in command_lookup:
                raise ValueError(f"Invalid range: end ID '{end_id}' does not exist.")

            # Get indices of start and end IDs
            start_index = command_keys.index(start_id)
            end_index = command_keys.index(end_id)

            if start_index > end_index:
                raise ValueError(f"Invalid range: in '{cid}', start ID '{start_id}' comes after end ID '{end_id}'.")

            # Add commands in the specified range
            for cmd in commands[start_index:end_index + 1]:
                if cmd['id'] not in selected_ids:
                    selected_commands.append(cmd)
                    selected_ids.add(cmd['id'])

        elif cid == '*':
            # Handle '*' to select all commands
            for cmd in commands:
                if cmd['id'] not in selected_ids:
                    selected_commands.append(cmd)
                    selected_ids.add(cmd['id'])
            break  # No need to process further as all commands are selected

        elif cid.endswith('*') and len(cid) > 1:
            # Handle 'cmd1*' to select all commands from 'cmd1' to the end
            start_id = cid[:-1].strip()
            if start_id not in command_lookup:
                raise ValueError(f"Invalid wildcard command ID: '{cid}'. Start ID '{start_id}' does not exist.")

            start_index = command_keys.index(start_id)

            for cmd in commands[start_index:]:
                if cmd['id'] not in selected_ids:
                    selected_commands.append(cmd)
                    selected_ids.add(cmd['id'])
            break  # Wildcard selects all from start_id onwards

        elif cid in command_lookup:
            # Handle exact command ID matches
            if cid not in selected_ids:
                selected_commands.append(command_lookup[cid])
                selected_ids.add(cid)
        else:
            # Invalid command ID
            raise ValueError(f"Invalid command ID: '{cid}'. Please provide a valid command ID from the instruction file.")

    return selected_commands

def copy_source_files(source_paths: List[str], target_dir: Path):
    """
    Copies source files matching the given patterns to the target directory.
    Only copies if the target directory is created or is empty.

    :param source_paths: List of glob patterns for source files.
    :param target_dir: Path object representing the target directory.
    """
    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
        copy_files(source_paths, target_dir)
    else:
        if not any(target_dir.iterdir()):
            copy_files(source_paths, target_dir)
        else:
            logging.info(f"Target directory '{target_dir}' exists and is not empty. Skipping source file copy.")


def copy_files(patterns: List[str], target_dir: Path):
    """
    Copies files matching the patterns to the target directory.

    :param patterns: List of glob patterns.
    :param target_dir: Path object representing the target directory.
    """
    for pattern in patterns:
        # Resolve glob patterns relative to the current working directory
        matched_files = list(Path('.').glob(pattern))
        for src in matched_files:
            if src.is_file():
                dest = target_dir / src.name
                shutil.copy2(src, dest)
                logging.debug(f"Copied '{src}' to '{dest}'.")


def setup_logging(target_dir: Path, debug: bool = False) -> LoggerManager:
    """
    Sets up logging by creating the 'log' directory within the target directory.

    :param target_dir: Path object representing the target directory.
    :param debug: Boolean flag to enable debug logs to console.
    :return: Initialized LoggerManager instance.
    """
    log_dir = target_dir / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    return LoggerManager(log_dir, debug=debug)


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Execute LLM-based commands from an instruction TOML file.")
    parser.add_argument("instruction_file", type=str, help="Path to the instructions.toml file.")
    parser.add_argument("command_ids", type=str, nargs='+', help="Command IDs to execute. Supports multiple IDs separated by spaces (e.g., 'create_converteggstocsv another_command').")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging to console.")
    args = parser.parse_args()

    instruction_path = Path(args.instruction_file).resolve()
    if not instruction_path.is_file():
        print(f"Error: Instruction file '{instruction_path}' does not exist.")
        sys.exit(1)

    try:
        # Initialize LoggerManager with a temporary log directory for initial steps
        temp_log_dir = Path("./log_temp")
        temp_log_dir.mkdir(parents=True, exist_ok=True)
        temp_logger_manager = LoggerManager(temp_log_dir, debug=args.debug)

        # Parse and validate instruction file
        parser_obj = InstructionParser(instruction_path)
        data = parser_obj.get_data()

        # Process directives
        source_paths = data.get("source", {}).get("paths", [])
        target_directory = Path(data.get("target", {}).get("directory", "output")).resolve()
        copy_source_files(source_paths, target_directory)

        # Reinitialize LoggerManager with actual target directory and debug flag
        logger_manager = setup_logging(target_directory, debug=args.debug)

        # Initialize MacroResolver
        shared_prompts = data.get("shared_prompts", {})
        macro_resolver = MacroResolver(shared_prompts)

        # Initialize ContextManager
        context_manager = ContextManager(target_directory)

        # Initialize LLMBot
        llm_bot = LLMBot()

        # Parse command_ids and map to commands
        commands = data.get("commands", [])
        if not commands:
            raise LLMRunError("No commands found in the instruction file.")

        selected_commands = parse_command_ids(args.command_ids, commands)

        if not selected_commands:
            raise LLMRunError("No valid commands selected for execution.")
        
        # Initialize and execute selected commands
        command_executor = CommandExecutor(
            instruction_data=data,
            instruction_dir=instruction_path.parent,
            target_dir=target_directory,
            logger_manager=logger_manager,
            llm_bot=llm_bot,
            macro_resolver=macro_resolver,
            context_manager=context_manager,
            selected_commands=selected_commands,
            max_workers=10  # Adjust based on your system and OpenAI rate limits
        )
        command_executor.execute_all()

    except LLMRunError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}\n{traceback.format_exc()}")
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
