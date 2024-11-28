from typing import List, Dict, Any
import os
from pathlib import Path
import logging
import subprocess
import re
import traceback
import concurrent.futures

from llmbatcheditor.LLMRunError import LLMRunError
from llmbatcheditor.LLMEndPoint import LLMEndPoint
from llmbatcheditor.InstructionParser import InstructionParser
from llmbatcheditor.LoggerManager import LoggerManager
from llmbatcheditor.ContextManager import ContextManager
from llmbatcheditor.MacroResolver import MacroResolver

class CommandExecutor:
    """Executes a single command as per the instruction file."""

    def __init__(self, command: Dict[str, Any], instruction_data: Dict[str, Any], instruction_dir: Path, target_dir: Path,
                 logger_manager: LoggerManager, llm_end_point: LLMEndPoint, macro_resolver: MacroResolver,
                 context_manager: ContextManager, max_workers: int = 5):
        self.command = command
        self.defaults = instruction_data.get("defaults", {})
        self.shared_prompts = instruction_data.get("shared_prompts", {})
        self.instruction_dir = instruction_dir
        self.target_dir = target_dir
        self.logger_manager = logger_manager
        self.llm_end_point = llm_end_point
        self.macro_resolver = macro_resolver
        self.context_manager = context_manager
        self.max_workers = max_workers  # Maximum number of threads for parallel processing

    def execute(self):
        cmd_id = self.command.get("id")
        cmd_type = self.command.get("type")
        logger = self.logger_manager.setup_command_logger(cmd_id)
        logger.info(f"Starting command '{cmd_id}' of type '{cmd_type}'.")

        try:
            if cmd_type == "llm_create":
                self.execute_llm_create(self.command, logger)
            elif cmd_type == "llm_edit":
                self.execute_llm_edit(self.command, logger)
            elif cmd_type == "llm_feedback_edit":
                self.execute_llm_feedback_edit(self.command, logger)
            else:
                raise LLMRunError(f"Unsupported command type '{cmd_type}' in command '{cmd_id}'.")

            logger.info(f"Command '{cmd_id}' completed successfully.")
            print(f"Command '{cmd_id}': OK")
        except Exception as e:
            logger.error(f"Command '{cmd_id}' failed with error: {e}\n{traceback.format_exc()}")
            print(f"Command '{cmd_id}': ERROR")

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
        llm_response = self.llm_end_point.get_response([{"role": "user", "content": full_prompt}], model=model)

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
        llm_response = self.llm_end_point.get_response([{"role": "user", "content": full_prompt}], model=model)

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
                llm_response = self.llm_end_point.get_response([{"role": "user", "content": full_prompt}], model=model)

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
