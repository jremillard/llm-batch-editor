from typing import List, Dict, Any

import logging
from pathlib import Path
import sys

from llmbatcheditor.LLMRunError import LLMRunError


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

    def setup_file_loggers(self, command_id: str, file_name: str, cycle:int = 0) -> Dict[str, logging.Logger]:
        """
        Sets up loggers for LLM prompt and output for a specific file.
        Returns a dictionary with 'prompt' and 'output' loggers.
        """

        if ( cycle <= 0):
            prompt_logger = logging.getLogger(f"{command_id}.{file_name}.llm-prompt")
            output_logger = logging.getLogger(f"{command_id}.{file_name}.llm-output")
        else:
            prompt_logger = logging.getLogger(f"{command_id}.{file_name}.{cycle}.llm-prompt")
            output_logger = logging.getLogger(f"{command_id}.{file_name}.{cycle}.llm-output")

        # Remove existing handlers
        if prompt_logger.hasHandlers():
            prompt_logger.handlers.clear()
        if output_logger.hasHandlers():
            output_logger.handlers.clear()

        # Prompt logger
        if ( cycle <= 0):
            prompt_file = self.log_dir / f"{command_id}.{file_name}.llm-prompt.txt"
        else:
            prompt_file = self.log_dir / f"{command_id}.{file_name}.{cycle}.llm-prompt.txt"
            
        ph = logging.FileHandler(prompt_file, mode='w', encoding='utf-8')
        ph.setLevel(logging.DEBUG)
        ph.setFormatter(logging.Formatter("%(message)s"))
        prompt_logger.addHandler(ph)
        prompt_logger.propagate = False

        # Output logger
        if ( cycle <= 0):
            output_file = self.log_dir / f"{command_id}.{file_name}.llm-output.txt"
        else:
            output_file = self.log_dir / f"{command_id}.{file_name}.{cycle}.llm-output.txt"
            
        oh = logging.FileHandler(output_file, mode='w', encoding='utf-8')
        oh.setLevel(logging.DEBUG)
        oh.setFormatter(logging.Formatter("%(message)s"))
        output_logger.addHandler(oh)
        output_logger.propagate = False

        return {"prompt": prompt_logger, "output": output_logger}

    def delete_command_logs(self, command_id: str, file_name: str):
        """
        Deletes any log file that starts with {command_id}.{file_name}.
        """
        for log_file in self.log_dir.glob(f"{command_id}.{file_name}.*"):
            log_file.unlink()
