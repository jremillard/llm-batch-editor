from typing import List, Dict, Any

import logging
import os

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
