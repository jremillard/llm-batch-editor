# llm-batch-editor

An AI-powered tool to automate batch creation and editing of text files/source code.

## Purpose

`llmrun.py` is a Python script designed to interpret and execute commands from an instruction file (e.g., `instructions.toml`). It automates code generation, editing, testing, and execution tasks by leveraging Large Language Models (LLMs) and shell commands. This tool streamlines processes such as codebase transformation, documentation generation, automated debugging, and script execution. 

This project was written to learn the limits of the current AI models.

Licensed under the MIT License.

## Dependencies

Python 3.8+ is required. 
You can install the required packages using the following command:
```bash
pip install -r requirements.txt
```
## Command-Line Interface

**Usage:**
```bash
python [llmrun.py] instructions.toml command1-ids [command2-ids] ...
```

