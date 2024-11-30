from typing import List, Dict, Any

import logging
import os
import time

from pathlib import Path

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
        filelist = []
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
        file_data = self.load_file_data(patterns)
        return self.format_context_items(file_data)

    def load_file_data(self, patterns: List[str]) -> List[Dict[str, Any]]:
        """
        Loads file data based on glob patterns into a list of dictionaries.
        Each dictionary contains the filename and content as a string or formatted binary data.
        Args:
            patterns (List[str]): A list of glob patterns to match files in the target directory.
        Returns:
            List[Dict[str, Any]]: A list of dictionaries, each containing:
                - "filename" (str): The relative path of the file from the target directory.
                - "content" (str): The content of the file as a string. For text files, this is the file's text content.
                                   For binary files, this is a formatted string with ASCII and hexadecimal representations.
                - "modified_time" (int): The modified time of the file in nanoseconds.
        """
        file_data = []
        for pattern in patterns:

            if pattern == "{{filelist}}":
                file_data.append({"filename": "list of file names", "content": self.generate_filelist()})
                continue

            matched_files = list(self.target_directory.glob(pattern))
            for file_path in matched_files:
                if file_path.is_file():
                    file_info = {"filename": os.path.relpath(file_path, self.target_directory)}
                    file_info["modified_time"] = file_path.stat().st_mtime_ns  

                    is_binary = file_path.suffix.lower() in BINARY_EXTENSIONS

                    if ( not is_binary ):
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                file_info["content"] = f.read()
                        except UnicodeDecodeError:
                            is_binary = True

                    if is_binary:
                        with open(file_path, 'rb') as f:
                            content = []
                            while True:
                                chunk = f.read(40)
                                if not chunk:
                                    break
                                ascii_part = ''.join(chr(byte) if 32 <= byte <= 126 else '.' for byte in chunk)
                                hex_part = ' '.join(f"{byte:02x}" for byte in chunk)
                                content.append(f"{ascii_part:<40} {hex_part}")
                            file_info["content"] = "\n".join(content)

                    file_data.append(file_info)
        return file_data

    def format_context_items(self, file_data: List[Dict[str, Any]]) -> List[str]:
        """
        Converts the list of file data hashes into a formatted list of context items.
        """
        context_items = []
        for file_info in file_data:
            context_items.append('-' * 80)
            context_items.append(f"File: {file_info['filename']}")
            context_items.append('-' * 80)
            context_items.append(file_info["content"])
        return context_items

