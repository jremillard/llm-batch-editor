# llm-batch-editor

An AI-powered tool to automate batch creation and editing of text files/source code.

## Purpose

`llmbatchedit.py` Uses Large Language Models (LLMs) to automate the creation and editing of text files. The sweet spot is for performing repeatable, automated, multi step operations across many files. The configuration for these operations is specified in an instruction file (e.g., `instructions.toml`).

This project was created to explore the limits of current AI models use in fully automating complex software development tasks.

Licensed under the MIT License.

## Instruction toml file.

Create file1.py and file2.py by porting pascal file1.pas and file2.pas to python, use gpt-4o, use the directory called output as the working directory.

```toml
[target]
directory = "output"

[defaults]
model = "gpt-4o"
prompt_model = "gpt-4o" 

[shared_prompts]

[[commands]]
id = "create_python"
type = "llm_create"
target_files = ["file1.py","file2.py"]
instruction = """
Convert the file {{filename_base}}.pas to file `{{filename_base}}.py`.
The converted file should use Python 3.
Verify that every function and procedure has a corresponding converted function.
Use type python hinting.
"""
context = ["*.pas", "*.csv"]
```

See `llmbatchedit.md` for full documentation on the `instructions.toml` and `llmbatchedit.py` command line arguments.

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
python [llmbatchedit.py] instructions.toml command1-ids [command2-ids] ...
