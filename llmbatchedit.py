from typing import List, Dict, Any
import argparse
import sys
from pathlib import Path
import logging
import traceback

from llmbatcheditor.LLMRunError import LLMRunError
from llmbatcheditor.LLMEndPoint import LLMEndPoint
from llmbatcheditor.LLMEndPointCached import LLMEndPointCached

from llmbatcheditor.InstructionParser import InstructionParser
from llmbatcheditor.LoggerManager import LoggerManager
from llmbatcheditor.ContextManager import ContextManager
from llmbatcheditor.MacroResolver import MacroResolver
from llmbatcheditor.CommandExecutor import CommandExecutor

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
        output_dir = Path(f"./.{Path(__file__).stem}/{instruction_path.stem}")
        log_dir = Path(f"{output_dir}/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        logger_manager = LoggerManager(log_dir, debug=args.debug)

        # Parse and validate instruction file
        parser_obj = InstructionParser(instruction_path)
        data = parser_obj.get_data()

        # Process directives
        target_directory = Path(data.get("target", {}).get("directory", "output")).resolve()

        # Initialize MacroResolver
        shared_prompts = data.get("shared_prompts", {})
        macro_resolver = MacroResolver(shared_prompts)

        # Initialize ContextManager
        context_manager = ContextManager(target_directory)

        # Initialize LLM End Point
        llm_end_point = LLMEndPointCached(cache_dir=Path(f"{output_dir}/cache"))

        # Parse command_ids and map to commands
        commands = data.get("commands", [])
        if not commands:
            raise LLMRunError("No commands found in the instruction file.")

        selected_commands = parse_command_ids(args.command_ids, commands)
 
        if not selected_commands:
            raise LLMRunError("No valid commands selected for execution.")
        
        # Initialize and execute selected commands
        for command in selected_commands:
            command_executor = CommandExecutor.create_executor(
                command=command,
                instruction_data=data,
                instruction_dir=instruction_path.parent,
                target_dir=target_directory,
                logger_manager=logger_manager,
                llm_end_point=llm_end_point,
                macro_resolver=macro_resolver,
                context_manager=context_manager,
                max_workers=3  # Adjust based on your system and OpenAI rate limits
            )
            command_executor.execute()

    except LLMRunError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}\n{traceback.format_exc()}")
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
