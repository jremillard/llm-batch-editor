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
import json

import LLMBot
import InstructionParser
import LoggerManager
import ContextManager
import MacroResolver
from LLMRunError import LLMRunError


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
        # Initialize LoggerManager with a log directory based on instruction file name
        instruction_base_name = instruction_path.stem
        log_dir = Path(f"./{instruction_base_name}-logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        logger_manager = LoggerManager.LoggerManager(log_dir, debug=args.debug)

        # Parse and validate instruction file
        parser_obj = InstructionParser.InstructionParser(instruction_path)
        data = parser_obj.get_data()

        # Process directives
        target_directory = Path(data.get("target", {}).get("directory", "output")).resolve()

        # Initialize MacroResolver
        shared_prompts = data.get("shared_prompts", {})
        macro_resolver = MacroResolver.MacroResolver(shared_prompts)

        # Initialize ContextManager
        context_manager = ContextManager.ContextManager(target_directory)

        # Initialize LLMBot
        llm_bot = LLMBot.LLMBot()

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
