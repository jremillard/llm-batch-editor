from typing import List, Dict, Any
import os
from pathlib import Path
import logging
import subprocess
import re
import traceback
import concurrent.futures
import threading

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
    _preedit_lock = threading.Lock()
    
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
        """Pre-edits the given instruction to format it as a Markdown list.
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

        with self._preedit_lock:
            preedit_prompt = """These are instructions to a software engineer. 
Convert them to a standard form which is: first the high-level instructions, then followed by check list. 
Don't duplicate information in the instructions and check list. 
Perfer to put details in the check list. 
Write the instructions so they are short and professional. 
Ensure that all relevant information is captured accurately in the checklist to avoid missing any critical details.
Don't add any checklist items for CI's, READMEs, best practices, performance, or unit tests unless included in the orginal instructions..
----------------------------------

"""
            
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
        
        # expand shared prompts, then edit the instruction with the prompt model 
        llm_edited_instruction = self.preedit_instruction(
            self.macro_resolver.resolve_shared_prompts(instruction), 
            model=prompt_model)

        # Resolve placeholders in the edited intructions
        placeholders = {
            "filename": file_name,
            "filename_base": os.path.splitext(file_name)[0],
            "filelist": self.context_manager.generate_filelist()
        }        
        resolved_instruction = self.macro_resolver.resolve_placeholders(llm_edited_instruction, placeholders)

        # Gather file context 
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

        # expand shared prompts, then edit the instruction with the prompt model 
        llm_edited_instruction = self.preedit_instruction(
            self.macro_resolver.resolve_shared_prompts(instruction), 
            model=prompt_model)

        # Resolve placeholders in the edited intructions
        placeholders = {
            "filename": file_name,
            "filename_base": os.path.splitext(file_name)[0],
            "filelist": self.context_manager.generate_filelist()
        }
        resolved_instruction = self.macro_resolver.resolve_placeholders(llm_edited_instruction, placeholders)

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
            raise

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
                future.result()
                logger.info(f"Feedback-editing completed successfully for '{file_name}'.")

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

        # clean out any old lots file for this command+file.
        self.logger_manager.delete_command_logs(logger.name,file_name)
        
        context_files = []
        prompt = []
        
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

                # expand shared prompts, then edit the instruction with the prompt model 
                llm_edited_instruction = self.preedit_instruction(
                    self.macro_resolver.resolve_shared_prompts(instruction), 
                    model=prompt_model)

                # Resolve placeholders in the edited intructions
                placeholders = {
                    "filename": file_name,
                    "filename_base": os.path.splitext(file_name)[0],
                    "filelist": self.context_manager.generate_filelist()
                }
                resolved_instruction = self.macro_resolver.resolve_placeholders(llm_edited_instruction, placeholders)

                context_items = []

                # command(s) output
                context_items.append('-'*80) 
                context_items.append(f"Output:")
                context_items.append('-'*80) 
                context_items.append(combined_output)

                # the file being edited.
                context_items.append('-'*80) 
                context_items.append(f"File: {file_name} Revision: {retry_count}")
                context_items.append('-'*80) 

                # Gather context, including the current file content
                try:
                    with open(target_file_path, 'r', encoding='utf-8') as f:
                        current_content = f.read()
                except Exception as e:
                    logger.error(f"Failed to read file '{file_name}' during feedback-edit: {e}")
                    break

                context_items.append(current_content)

                context_files_cycle = self.context_manager.load_file_data(context_patterns)

                # Add context files to the context_items list, ensuring no duplicates.
                # Skip the file currently being edited and any files already included in context_files.

                # Don't emit the edit file, and the content did not change    
                for context_file_cyle in context_files_cycle:
                    skip = False

                    if context_file_cyle['filename'] == file_name:
                        skipe = True                    
                    for context_file in context_files:
                        if context_file['filename'] == context_file_cyle['filename'] and context_file['modified_time'] == context_file_cyle['modified_time']:
                            skip = True

                    if ( not skip ):
                        context_items.append('-'*80) 
                        context_items.append(f"File: {context_file_cyle['filename']} Revision: {retry_count}")
                        context_items.append('-'*80) 
                        context_items.append(context_file_cyle["content"])

                        context_files.append(context_file_cyle)

                full_prompt = resolved_instruction + "\n" + "\n".join(context_items)

                # Log prompt
                file_loggers = self.logger_manager.setup_file_loggers(logger.name, file_name,retry_count)

                file_loggers["prompt"].info(full_prompt)

                # Get LLM response from API.
                prompt.append({"role": "user", "content": full_prompt})
                llm_response = self.llm_end_point.get_response(prompt, model=model)

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
                raise 

        if success:
            logger.info(f"Feedback-editing completed successfully for '{file_name}'.")
        else:
            raise LLMRunError(f"Feedback-editing failed for '{file_name}' after {max_retries} attempts.")
