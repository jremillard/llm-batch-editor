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
    """
    Base class for executing commands. Provides common functionality for different types of command executors.
    """
    
    @staticmethod
    def create_executor(command: Dict[str, Any], instruction_data: Dict[str, Any], instruction_dir: Path, target_dir: Path,
                        logger_manager: LoggerManager, llm_end_point: LLMEndPoint, macro_resolver: MacroResolver,
                        context_manager: ContextManager, max_workers: int = 5):
        cmd_type = command.get("type")
        if cmd_type == "llm_create":
            return LLMCreateExecutor(command, instruction_data, instruction_dir, target_dir, logger_manager, llm_end_point, macro_resolver, context_manager, max_workers)
        elif cmd_type == "llm_edit":
            return LLMEditExecutor(command, instruction_data, instruction_dir, target_dir, logger_manager, llm_end_point, macro_resolver, context_manager, max_workers)
        elif cmd_type == "llm_feedback_edit":
            return LLMFeedbackEditExecutor(command, instruction_data, instruction_dir, target_dir, logger_manager, llm_end_point, macro_resolver, context_manager, max_workers)
        else:
            raise LLMRunError(f"Unsupported command type '{cmd_type}' in command '{command.get('id')}'.")

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

    def extract_content_to_write(self, file_name: str, llm_response: str) -> str:
        content_to_write = None
        if file_name.endswith('.md'):
            # If the file is a markdown file, assume the LLM response is the file content
            content_to_write = llm_response.strip()
        else:
            # For other file types, use regex to extract the longest code block
            code_blocks = re.findall(r"```[a-zA-Z0-9\+]*\n(.*?)```", llm_response, re.DOTALL)
            if code_blocks:
                content_to_write = max(code_blocks, key=len).strip()
        return content_to_write

    def preedit_instruction(self, instruction: str, model: str) -> str:
        """
        Pre-edits the given instruction to format it as a Markdown list.
        This method takes an instruction string and a model identifier, formats the instruction
        as a Markdown list, and sends it to the LLM endpoint to get a response. The response is
        then stripped of any leading or trailing whitespace and returned.
        Editing an LLM prompt before sending it to the model can improve the clarity and structure
        of the instructions, leading to more accurate and relevant responses from the model. By
        formatting the instructions as a Markdown list, the prompt becomes more organized and easier
        for the model to interpret.
        Args:
            instruction (str): The instruction string to be pre-edited.
            model (str): The identifier of the model to be used for generating the response.
        Returns:
            str: The response from the LLM endpoint after processing the formatted instruction.
        """
        preedit_prompt = "Format the instructions in MD. " + \
            "Make each requirement an item in a list. "+ \
            "Rewrite the requirements to be clear. " + \
            "Don't add new major requirements. "
            
        full_prompt = f"{preedit_prompt}\n\n{instruction}"
        
        # Get LLM response
        llm_response = self.llm_end_point.get_response([{"role": "user", "content": full_prompt}], model=model)
        
        return llm_response.strip()


class LLMCreateExecutor(CommandExecutor):
    """
    Executor for handling 'llm_create' commands. Creates new files based on LLM responses.
    """
    def __init__(self, command: Dict[str, Any], instruction_data: Dict[str, Any], instruction_dir: Path, target_dir: Path,
                 logger_manager: LoggerManager, llm_end_point: LLMEndPoint, macro_resolver: MacroResolver,
                 context_manager: ContextManager, max_workers: int = 5):
        super().__init__(command, instruction_data, instruction_dir, target_dir, logger_manager, llm_end_point, macro_resolver, context_manager, max_workers)

    def execute(self):
        cmd_id = self.command.get("id")
        logger = self.logger_manager.setup_command_logger(cmd_id)
        logger.info(f"Starting command '{cmd_id}' of type 'llm_create'.")

        try:
            self.execute_llm_create(self.command, logger)
            logger.info(f"Command '{cmd_id}' completed successfully.")
            print(f"Command '{cmd_id}': OK")
        except Exception as e:
            logger.error(f"Command '{cmd_id}' failed with error: {e}\n{traceback.format_exc()}")
            print(f"Command '{cmd_id}': ERROR")

    def execute_llm_create(self, command: Dict[str, Any], logger: logging.Logger):
        target_files = command.get("target_files", [])
        instruction = command.get("instruction", "")
        context_patterns = command.get("context", [])
        model = command.get("model", self.defaults.get("model", "gpt-4o"))
        prompt_model = command.get("prompt_model", self.defaults.get("prompt_model", "gpt-4o"))

        # Use ThreadPoolExecutor for parallel processing
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {
                executor.submit(self.process_create_file, file_name, instruction, context_patterns, model, prompt_model, logger): file_name
                for file_name in target_files
            }
            for future in concurrent.futures.as_completed(future_to_file):
                file_name = future_to_file[future]
                try:
                    future.result()
                    logger.info(f"File '{file_name}' created successfully.")
                except Exception as e:
                    logger.error(f"Error creating file '{file_name}': {e}")

    def process_create_file(self, 
            file_name: str, 
            instruction: str, 
            context_patterns: List[str], 
            model: str, 
            prompt_model: str, 
            logger: logging.Logger):
        logger.info(f"Creating file '{file_name}'.")
        placeholders = {
            "filename": file_name,
            "filename_base": os.path.splitext(file_name)[0],
            "output": "",
            "filelist": self.context_manager.generate_filelist()
        }
        preedited_instruction = self.preedit_instruction(instruction, model=prompt_model)
        resolved_instruction = self.macro_resolver.resolve(preedited_instruction, placeholders)

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
        content_to_write = self.extract_content_to_write(file_name, llm_response)
 
        # Write to target file
        target_file_path = self.target_dir / file_name
        with open(target_file_path, 'w', encoding='utf-8') as f:
            f.write(content_to_write)

class LLMEditExecutor(CommandExecutor):
    """
    Executor for handling 'llm_edit' commands. Edits existing files based on LLM responses.
    """
    def __init__(self, command: Dict[str, Any], instruction_data: Dict[str, Any], instruction_dir: Path, target_dir: Path,
                 logger_manager: LoggerManager, llm_end_point: LLMEndPoint, macro_resolver: MacroResolver,
                 context_manager: ContextManager, max_workers: int = 5):
        super().__init__(command, instruction_data, instruction_dir, target_dir, logger_manager, llm_end_point, macro_resolver, context_manager, max_workers)

    def execute(self):
        cmd_id = self.command.get("id")
        logger = self.logger_manager.setup_command_logger(cmd_id)
        logger.info(f"Starting command '{cmd_id}' of type 'llm_edit'.")

        try:
            self.execute_llm_edit(self.command, logger)
            logger.info(f"Command '{cmd_id}' completed successfully.")
            print(f"Command '{cmd_id}': OK")
        except Exception as e:
            logger.error(f"Command '{cmd_id}' failed with error: {e}\n{traceback.format_exc()}")
            print(f"Command '{cmd_id}': ERROR")

    def execute_llm_edit(self, command: Dict[str, Any], logger: logging.Logger):
        target_files = command.get("target_files", [])
        instruction = command.get("instruction", "")
        context_patterns = command.get("context", [])
        model = command.get("model", self.defaults.get("model", "gpt-4"))
        prompt_model = command.get("prompt_model", self.defaults.get("prompt_model", "gpt-4o"))

        # Use ThreadPoolExecutor for parallel processing
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {
                executor.submit(self.process_edit_file, file_name, instruction, context_patterns, model, prompt_model, logger): file_name
                for file_name in target_files
            }
            for future in concurrent.futures.as_completed(future_to_file):
                file_name = future_to_file[future]
                try:
                    future.result()
                    logger.info(f"File '{file_name}' edited successfully.")
                except Exception as e:
                    logger.error(f"Error editing file '{file_name}': {e}")

    def process_edit_file(self, 
            file_name: str, 
            instruction: str, 
            context_patterns: List[str], 
            model: str, 
            prompt_model: str, 
            logger: logging.Logger):
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
        preedited_instruction = self.preedit_instruction(instruction, model=prompt_model)
        resolved_instruction = self.macro_resolver.resolve(preedited_instruction, placeholders)

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

        content_to_write = self.extract_content_to_write(file_name, llm_response)
 
        # Write updated content to the file
        with open(target_file_path, 'w', encoding='utf-8') as f:
            f.write(content_to_write)

class LLMFeedbackEditExecutor(CommandExecutor):
    """
    Executor for handling 'llm_feedback_edit' commands. Edits files based on feedback from test commands and LLM responses.
    """
    def __init__(self, command: Dict[str, Any], instruction_data: Dict[str, Any], instruction_dir: Path, target_dir: Path,
                 logger_manager: LoggerManager, llm_end_point: LLMEndPoint, macro_resolver: MacroResolver,
                 context_manager: ContextManager, max_workers: int = 5):
        super().__init__(command, instruction_data, instruction_dir, target_dir, logger_manager, llm_end_point, macro_resolver, context_manager, max_workers)

    def execute(self):
        cmd_id = self.command.get("id")
        logger = self.logger_manager.setup_command_logger(cmd_id)
        logger.info(f"Starting command '{cmd_id}' of type 'llm_feedback_edit'.")

        try:
            self.execute_llm_feedback_edit(self.command, logger)
            logger.info(f"Command '{cmd_id}' completed successfully.")
            print(f"Command '{cmd_id}': OK")
        except Exception as e:
            logger.error(f"Command '{cmd_id}' failed with error: {e}\n{traceback.format_exc()}")
            print(f"Command '{cmd_id}': ERROR")

    def execute_llm_feedback_edit(self, command: Dict[str, Any], logger: logging.Logger):
        target_files = command.get("target_files", [])
        instruction = command.get("instruction", "")
        test_commands = command.get("test_commands", [])
        max_retries = command.get("max_retries", 3)
        context_patterns = command.get("context", [])
        model = command.get("model", self.defaults.get("model", "gpt-4"))
        prompt_model = command.get("prompt_model", self.defaults.get("prompt_model", "gpt-4o"))

        # Use ThreadPoolExecutor for parallel processing
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {
                executor.submit(self.process_feedback_edit_file, file_name, instruction, test_commands, max_retries, context_patterns, model, prompt_model, logger): file_name
                for file_name in target_files
            }
            for future in concurrent.futures.as_completed(future_to_file):
                file_name = future_to_file[future]
                try:
                    future.result()
                    logger.info(f"Feedback-editing completed successfully for '{file_name}'.")
                except Exception as e:
                    logger.error(f"Feedback-editing failed for '{file_name}': {e}")

    def process_feedback_edit_file(
            self, 
            file_name: str, 
            instruction: str, 
            test_commands: List[str], 
            max_retries: int,
            context_patterns: List[str], 
            model: str, 
            prompt_model: str,
            logger: logging.Logger):
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
                preedited_instruction = self.preedit_instruction(instruction, prompt_model)
                resolved_instruction = self.macro_resolver.resolve(preedited_instruction, placeholders)

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

                content_to_write = self.extract_content_to_write(file_name, llm_response)
        
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
