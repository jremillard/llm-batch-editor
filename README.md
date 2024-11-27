# llm-batch-editor

An AI-powered tool to automate batch creation and editing of text files/source code.

## Purpose

`llmrun.py` is a Python script designed to interpret and execute commands from an instruction file (e.g., `instructions.toml`). It automates code generation, editing, testing, and execution tasks by leveraging Large Language Models (LLMs) and shell commands. This tool streamlines processes such as codebase transformation, documentation generation, automated debugging, and script execution. 

This project was written to learn the limits of the current AI models.

Licensed under the MIT License.

## Instructions

The `instructions.toml` file contains a series of LLM commands that `llmrun.py` interprets and executes. These commands can include tasks such as generating new code, editing existing code, running tests, and executing scripts. The program supports context generation, allowing the LLM to maintain state across multiple commands. Modular prompts enable the reuse of common command patterns. Concurrent execution allows multiple commands to be processed simultaneously. 

See `llmrun.md` for full documentation on the `instructions.toml` and `llmrun.py` command line arguments.

## Dependencies

- It was written using Python 3.10.
- Install the required packages using the following command:
    ```bash
    pip install -r requirements.txt
    ```
- At least one LLM API key is required:
  - An OpenAI API key set in the environment variable `OPENAI_API_KEY`.
  - An Anthropic API key set in the environment variable `ANTHROPIC_API_KEY`.

## Command-Line Interface

**Usage:**
```bash
python [llmrun.py] instructions.toml command1-ids [command2-ids] ...
