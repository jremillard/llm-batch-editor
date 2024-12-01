# `llmbatchedit` Specification 

## Purpose

`llmbatchedit.py` uses Large Language Models (LLMs) to automate the creation and editing of text files. The sweet spot is for performing repeatable, automated, multi-step operations across many files. The configuration for these operations is specified in an instruction file (e.g., `instructions.toml`).

---

## Command-Line Interface

**Usage:**
```bash
python llmbatchedit.py instructions.toml command [command2] ...
```

- **`instructions`**: Path to the TOML instruction file containing directives and commands. This is required.
- **`commands`**: Specifies which commands to run. At least one command ID must be specified.

**Command Syntax:**

- **Single command** (`ID`): Runs only command `ID`.
- **Multiple commands** (`ID1 ID2 ID3`): Runs the three commands.
- **Range** (`ID1-ID3`): Runs commands from `ID1` to `ID3`, inclusive.
- **Open-Ended Range** (`ID-`): Runs commands from `ID` to the last command in the instruction file.

---

## Instruction File Structure (`instructions.toml`)

The instruction file is structured using [TOML](https://toml.io/en/) (Tom's Obvious, Minimal Language). The top-level directives are **target**, **defaults**, **shared prompts (macros)**, and an ordered list of **commands**.

### 1. Target

- **`target.directory`**: Specifies the output directory for the project. The target directory will be created if it does not exist. Note that the software will edit and overwrite the files in this directory; please keep a backup or use revision control.

```toml
[target]
directory = "output-directory"
[defaults]
...
[shared_prompts]
...
[[commands]]
...
```

### 2. Defaults

**Purpose:** Define default settings that apply to all commands unless explicitly overridden. This promotes consistency and reduces redundancy in the configuration.

- **`defaults.model`**: Specifies the default LLM to use for commands that do not explicitly define a `model`. This setting ensures that all commands have a consistent LLM unless overridden individually.

- **`defaults.prompt_model`**: Specifies the default LLM to use for pre-editing instructions before they are resolved and sent to the main `model`. 

```toml
[target]
...
[defaults]
model = "gpt-4o"
prompt_model = "gpt-4o"
[shared_prompts]
...
[[commands]]
...
```

### 3. Commands

Commands are defined in an ordered list and executed sequentially. Each command has a unique `id` string identifier and a specific type with associated parameters.

```toml
[target]
...
[defaults]
...
[shared_prompts]
...
[[commands]]
id = "initialize_project"
type = "llm_create"
target_files = ["converter.py"]
instruction = """
Write a Python program {{filename}} that converts all JSON files in the directory into CSV files.
{{error_handling}}
{{commenting}}
"""
context = ["*.json", "*.md"]
```

#### General Command Schema

- **`command.id`**
  - **Description:** A unique identifier for the command. Commands are executed in the order they appear in the file, allowing dependencies to be expressed.
  - **Example:** `"initialize_project"`

- **`command.type`**
  - **Description:** Specifies the command type. Supported types:
    - `llm_create`
    - `llm_edit`
    - `llm_feedback_edit`

    See the next section for details on the command types.

- **`command.target_files`**
  - **Type:** Array of strings
  - **Description:** Names of files to create. If multiple target files are specified, the LLM requests are processed in parallel to increase speed.
  - **Example:** `["converter.py"]`

- **`command.instruction`**
  - **Type:** Multiline String with Macros
  - **Description:** Instructions to be provided to the LLM. May contain placeholders like `{{filename}}`, `{{filename_base}}`, and macros like `{{macro_name}}`, which will be replaced with shared prompt snippets.
  - **Example:**
    ```toml
    instruction = """
    Write a Python program {{filename}} that converts all JSON files in the directory into CSV files.
    {{error_handling}}
    {{commenting}}
    """
    ```

- **`command.context`**
  - **Type:** Array of strings
  - **Description:** Specifies files or items to include in the LLM context. Context is a list allowing multiple files to be included in the context.
  - **Example:** `["*.json", "*.md"]`

- **`command.model`** *(Optional)*: Specifies the LLM to use. If omitted, the `defaults.model` value is used.

- **`command.prompt_model`** *(Optional)*: Specifies the LLM to use for prompt rewriting. If omitted, the `defaults.prompt_model` value is used.

#### Command Types and Parameters

##### A. LLM Create Commands (`command.type = llm_create`)

**Purpose:** Use an LLM to create new files based on provided instructions and context. The code block in the language model output is extracted and used to generate the content of the new target files.

##### B. LLM Edit Commands (`command.type = llm_edit`)

**Purpose:** Use a language model to edit existing files based on the provided instructions and context. The output from the language model is used to modify the content of the target files.

##### C. LLM Feedback-Edit Commands (`command.type = llm_feedback_edit`)

**Purpose:** Automate code correction by running one or more shell commands, capturing all output, and using the LLM to fix any issues found. This command tracks the history of the edits and command outputs in its LLM conversation history.

- **`command.test_commands`**
  - **Type:** Array of strings
  - **Description:** Commands to execute that test the code. May include the `{{filename}}` placeholder. Error return codes from `test_commands` do not result in an error in the processing. The current directory of the scripts is the target directory.
  - **Example:** `["python {{filename}}"]`

- **`command.max_retries`**
  - **Description:** Maximum number of iterations to attempt fixing issues.
  - **Example:** `3`

## Context Handling

All command types support the `command.context` tag. The context provides additional information to the LLM to improve the performance of the task. The listed files are presented in their entirety to the LLM in the prompt. The script does not have any RAG functionality.

**Context Items:**

- **File Patterns**: e.g., `*.py`, `docs/*.md` (patterns are resolved relative to the target directory).
- **Specific Files**: e.g., `utils.py`
- **Special Tokens (enclosed in curly braces):** e.g., `{{filelist}}`

**Example Usage in Commands:**
```toml
context = ["*.py", "*.md", "{{filelist}}"]
```

### 3. Macros

Instructions and context can include these macros. 

**Built-in Macros:**
- **`{{filename}}`**: Automatically replaced with the current target file's name during command execution. Used in instructions and shell commands.
- **`{{filename_base}}`**: Automatically replaced with the current target file's name stem during command execution. Used in instructions and shell commands.
- **`{{filelist}}`**: A generated list of files in the target directory with their sizes. The `__pycache__` directories are excluded. The program includes a built-in list of binary file extensions.

### 4. Shared Prompts

**Purpose:** Define reusable prompt snippets that can be embedded within instruction texts. This allows for fine-grained reuse of common instruction components without requiring full prompt duplication.

**Guidelines for Custom Macros:**
- **Naming Conventions:** Use descriptive names in lowercase with underscores (e.g., `error_handling`).
- **Avoid Conflicts:** Do **not** define a shared prompt with the same name as any built-in macro (`file`, `filename`, `filelist`). Attempting to do so will result in a fatal error.
- **Placeholders within Macros:** Custom macros can include placeholders like `{{filename}}`, `{{filename_base}}`, or `{{filelist}}`, which will be substituted during execution.

```toml
[shared_prompts]
commenting = "Include proper comments explaining the code."
error_handling = "Ensure proper error handling is implemented."
docstring_improvement = "Enhance the docstrings to follow PEP 257 conventions."
```

- **`shared_prompts.<macro_name>`**
  - **Description:** Defines a reusable prompt snippet identified by `<macro_name>`.
  - **Example:**
    ```toml
    [shared_prompts]
    commenting = "Include proper comments explaining the code."
    ```

**Referencing Shared Prompts in Instructions:**

Within the `instruction` field of commands, shared prompts can be included using the macro syntax `{{macro_name}}`. During processing, these macros will be replaced with their corresponding shared prompt content.

**Supported Syntax for Macros:**
- **Inline Macros:** `{{macro_name}}` can be placed anywhere within the instruction text.
- **Multiple Instances:** The same macro can be used multiple times within an instruction. However, shared prompts cannot include other shared prompts.

**Instruction Placeholder Resolution Process:**

1. **Identify Macros:** Scan the `instruction` text for `{{macro_name}}` patterns.
2. **Replace Shared Prompts:** Replace each `{{macro_name}}` with its corresponding shared prompt content defined in `[shared_prompts]`.
3. **Substitute Placeholders:** After shared prompts are expanded, substitute built-in macros like `{{filename}}` with their respective values based on the command context.
4. **Final Instruction:** The fully resolved instruction is then sent to the LLM for rewriting.

**Example Resolution:**
Given the following shared prompt and command instruction:

```toml
[shared_prompts]
python_convert = "Write a Python program {{filename}} that converts all JSON files in the directory into CSV files."
error_handling = "Ensure proper error handling is implemented."
commenting = "Include proper comments explaining the code."
```

```toml
instruction = """
{{python_convert}}
{{error_handling}}
{{commenting}}
"""
```

**Step-by-Step Resolution:**
1. Replace `{{python_convert}}` with "Write a Python program {{filename}} that converts all JSON files in the directory into CSV files."
2. Replace `{{error_handling}}` with "Ensure proper error handling is implemented."
3. Replace `{{commenting}}` with "Include proper comments explaining the code."
4. Replace `{{filename}}` with the target file's name (e.g., `converter.py`). The filename will be processed last in case it was included as part of a shared prompt.

**Instruction:**
```
Write a Python program converter.py that converts all JSON files in the directory into CSV files.
Ensure proper error handling is implemented.
Include proper comments explaining the code.
```

The instructions are then sent to the LLM to be rewritten as a checklist.

---

## Sample Instruction Files

### **Instructions with Macros and Enhanced `{{filename}}` Token (`sample-instructions.toml`)**

```toml
[target]
directory = "output"

[defaults]
model = "gpt-4o"
prompt_model = "gpt-4o"

[shared_prompts]
error_handling = "Ensure proper error handling is implemented."
commenting = "Include proper comments explaining the code."
docstring_improvement = "Enhance the docstrings to follow PEP 257 conventions."
fix_compilation_errors = "Please fix any errors in {{filename}} to make it run successfully."

[[commands]]
id = "create_converter"
type = "llm_create"
target_files = ["converter.py"]
instruction = """
Write a Python program {{filename}} that converts all JSON files in the directory into CSV files.
{{error_handling}}
{{commenting}}
"""
context = ["*.json", "*.md"]

[[commands]]
id = "edit_docstrings"
type = "llm_edit"
target_files = ["utils.py"]
instruction = """
Improve the docstrings in {{filename}}.
{{docstring_improvement}}
"""
context = []

[[commands]]
id = "feedback_edit_converter"
type = "llm_feedback_edit"
target_files = ["converter.py"]
instruction = """
{{fix_compilation_errors}}
"""
test_commands = ["python {{filename}}"]
max_retries = 3
context = ["*.py", "*.md"]
```

### **Instructions for Adding Unit Tests with Shared Prompts and Default Model (`add-unit-tests.toml`)**

```toml
[target]
directory = "test"

[defaults]
model = "gpt-4o"
prompt_model = "gpt-4o"

[shared_prompts]
create_unit_tests = "For each Python module in the source directory, create a unit test file named {{filename}} using Python's built-in `unittest` framework."
fix_test_failures = "Please fix any issues in {{filename}} to ensure all tests run successfully."
create_readme_prompt = "Write a README.md file that explains how to run the unit tests for this Python project. Include instructions for setting up the environment, installing any dependencies, and running the tests. Mention any important details that developers should be aware of when working with the tests."
docstring_improvement = "Enhance the docstrings to follow PEP 257 conventions."

[[commands]]
id = "create_unit_tests"
type = "llm_create"
target_files = ["test_module1.py", "test_module2.py", "test_module3.py"]
instruction = """
{{create_unit_tests}}
"""
context = ["module1.py", "module2.py", "module3.py"]

[[commands]]
id = "feedback_edit_tests"
type = "llm_feedback_edit"
target_files = ["test_module1.py"]
instruction = """
The test file {{filename}} failed to run with the following error:
{{fix_test_failures}}
"""
test_commands = ["python -m unittest {{filename}}"]
max_retries = 2
context = ["module1.py", "module2.py", "module3.py"]

[[commands]]
id = "create_readme"
type = "llm_create"
target_files = ["README.md"]
instruction = """
{{create_readme_prompt}}
"""
context = ["test_module1.py", "test_module2.py", "test_module3.py"]

[[commands]]
id = "edit_modules"
type = "llm_edit"
target_files = ["module1.py", "module2.py", "module3.py"]
instruction = """
Improve the docstrings in {{filename}}.
{{docstring_improvement}}
"""
context = [""]

[[commands]]
id = "feedback_edit_pylint"
type = "llm_feedback_edit"
target_files = ["module1.py"]
instruction = """
The file {{filename}} has code quality issues as reported by pylint:
Please fix the issues in {{filename}} to improve code quality.
Focus on errors and warnings, and aim for a pylint score of at least 8.0.
"""
test_commands = ["pylint {{filename}}"]
max_retries = 1
context = [""]
```

### **Instructions for Converting Managed C++ to C# with Shared Prompts and Default Model (`cpp-to-cs.toml`)**

```toml
[target]
directory = "csharp"

[defaults]
model = "gpt-4o"
prompt_model = "gpt-4o"

[shared_prompts]
convert_cpp_to_cs = "Convert the Managed C++ files to equivalent C# files. Ensure that the functionality and logical structure are preserved."
fix_compilation_errors_cs = "Please fix any errors in {{filename}} to resolve the compilation errors."
create_cs_readme = "Write a README.md file explaining how the Managed C++ code was converted to C#. Include details on any significant changes made during the conversion process. Provide instructions for building the C# project and mention any dependencies required."

[[commands]]
id = "convert_cpp_classes"
type = "llm_create"
target_files = ["Class1.cs", "Class2.cs", "Utils.cs"]
instruction = """
{{convert_cpp_to_cs}}
"""
context = ["*.cpp"]

[[commands]]
id = "feedback_edit_cs_classes"
type = "llm_feedback_edit"
target_files = ["Class1.cs", "Class2.cs", "Utils.cs"]
instruction = """
The compilation of {{filename}} failed with the following errors:
{{fix_compilation_errors_cs}}
"""
test_commands = ["csc /target:library /out:ConvertedAssembly.dll {{filename}}"]
max_retries = 2
context = ["*.cs", "*.cpp"]

[[commands]]
id = "create_cs_readme"
type = "llm_create"
target_files = ["README.md"]
instruction = """
{{create_cs_readme}}
"""
context = ["Class1.cs", "Class2.cs", "Utils.cs"]

[[commands]]
id = "refactor_utils_cs"
type = "llm_edit"
target_files = ["Utils.cs"]
instruction = """
Refactor the utility functions in {{filename}} to make use of modern C# features such as LINQ and async/await where appropriate.
{{docstring_improvement}}
"""
context = []

[[commands]]
id = "feedback_edit_utils_cs"
type = "llm_feedback_edit"
target_files = ["Utils.cs"]
instruction = """
After refactoring, {{filename}} failed to compile with the following errors:
{{fix_compilation_errors_cs}}
"""
test_commands = ["csc /target:library /out:ConvertedAssembly.dll {{filename}}"]
max_retries = 1
context = []
```
