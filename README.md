# llm-batch-editor

An AI-powered tool to automate batch creation and editing of text files/source code.

## Purpose

`llmbatchedit.py` Uses Large Language Models (LLMs) to automate the creation and editing of text files. The sweet spot is for performing repeatable, automated, multi step operations across many files. The configuration for these operations is specified in an instruction file (e.g., `instructions.toml`).

This project was created to explore the limits of current AI models use in fully automating complex software development tasks.

Licensed under the MIT License.

## Instruction File

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
python llmbatchedit.py instructions.toml command1-ids [command2-ids] ...
```

## Why?

Since GPT-3.5 was released in November 2022, I've been attempting to automatically port a 4000 line personal program I wrote in Turbo Pascal back in 1989 to Python. It's an old-school text adventure game inspired by Zork and Adventure, set in my childhood neighborhood during Halloween 1988. It serves as an interesting test case because the source code is not available on the Internet, it uses the obsolete language (Turbo Pascal), and it runs on the obsolete operating system (MS-DOS).

This is my third attempt across different LLM generations. The first two attempts were complete failures—primarily due to the small context windows and the models not being advanced enough. 

However, as of December 2024, this third attempt, using the o1-preview model, is close. The main challenge now lies with one particularly long, 1,000+ line source file. The model struggles to reliably and repeatedly convert the long file without skipping functions or stopping. While some kind of splitting mechanism could be added, I would rather wait for the next generation of models to be released to see if the port will "just work" with this simple system for creating and editing files. 

It feels like a fully automated port will succeed soon.
