# `llmbatchedit` Specification 

## Purpose

`llmbatchedit.py` is a Python script designed to interpret and execute commands from an instruction file (e.g., `instructions.toml`). It automates code generation, editing, testing, and execution tasks by leveraging Large Language Models (LLMs) and shell commands. This tool streamlines processes such as codebase transformation, documentation generation, automated debugging, and script execution.

---

## Command-Line Interface

**Usage:**
```bash
python llmbatchedit.py instructions.toml command1 [command2] ...
```

- **`instructions.toml`**: Path to the TOML instruction file containing directives and commands.
- **`commands`**: Specifies which commands to run. 

**Command ids Syntax:**

- **Single command** (`ID`): Runs only command `ID`.
- **Comma-Separated command** (`ID1 ID2 ID2`): Runs commands `ID1`, `ID2`, `ID3`.
- **Range** (`ID1-ID3`): Runs commands from `ID1` to `ID3`, inclusive.
- **Open-Ended Range** (`ID-`): Runs commands from `ID` to the last command in the instruction file.

**Note:** The `command ids`is required. At least one command must be specified, If omitted, an error will be raised.
**Note:** The `instructions.toml` file argument is **required**. If omitted, an error will be raised.

---

## Instruction File Structure (`instructions.toml`)

The instruction file is structured using [TOML](https://toml.io/en/) (Tom's Obvious, Minimal Language), a configuration file format that is easy to read due to its simple syntax. The file comprises **directives**, **defaults**, **shared prompts (macros)**, and an ordered list of **commands**.

### 1. Directives

Directives target directory for the commands.

```toml

[target]

directory = "output"
```
- **`target.directory`**
  - **Type:** String
  - **Description:** Specifies the output directory for project. The target directory will be created if it does not exist. Note, software will edit and overwrite the files in this directory, please keep a backup.
  - **Example:**
    ```toml
    target.directory = "output"
    ```

### 2. Defaults

**Purpose:** Define default settings that apply to all commands unless explicitly overridden. This promotes consistency and reduces redundancy in the configuration.

```toml
[defaults]
model = "gpt-4o"
```

- **`defaults.model`**
  - **Type:** String
  - **Description:** Specifies the default LLM to use for commands that do not explicitly define a `model`. This setting ensures that all commands have a consistent LLM unless overridden individually.
  - **Example:**
    ```toml
    defaults.model = "gpt-4o"
    ```

- **`defaults.prompt_model`**
  - **Type:** String
  - **Description:** Specifies the default LLM to use for pre-editing instructions before they are resolved and sent to the main `model`. 
  - **Example:**
    ```toml
    defaults.prompt_model = "gpt-4o"
    ```

### 4. Commands

Commands are defined in an ordered list and executed sequentially. Each command has a unique `id` string identifier and a specific type with associated parameters.

```toml
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

- **`id`**
  - **Type:** String
  - **Description:** A unique identifier for the command. Commands are executed in the order they appear in the list.
  - **Example:** `"initialize_project"`

- **`type`**
  - **Type:** String
  - **Description:** Specifies the command type. Supported types:
    - `llm_create`
    - `llm_edit`
    - `llm_feedback_edit`
  - **Example:** `"llm_create"`

- **`model`** *(Optional)*
  - **Type:** String
  - **Description:** Specifies the LLM to use (e.g., `"gpt-4o"`). If omitted, the `defaults.model` value is used.
  - **Example:** `"gpt-4o"`

- **`instruction`**
  - **Type:** Multiline String with Macros
  - **Description:** Instructions to be provided to the LLM. May contain placeholders like `{{filename}}` and macros like `{{macro_name}}` which will be replaced with shared prompt snippets.
  - **Example:**
    ```toml
    instruction = """
    Write a Python program {{filename}} that converts all JSON files in the directory into CSV files.
    {{error_handling}}
    {{commenting}}
    """
    ```

#### Command Types and Parameters

##### A. LLM Create Commands (`llm_create`)

**Purpose:** Use a language model to create new files based on provided instructions and context. The output from the language model is used to generate the content of the new files.

**Schema:**
```toml
[[commands]]
id = "<unique_command_id>"
type = "llm_create"
target_files = ["<file_name1>", "<file_name2>", ...]
model = "<model_name>" # Optional: Uses defaults.model if omitted
instruction = """
<instruction_body with optional macros>
"""
context = ["<context_item1>", "<context_item2>", ...] 
```

- **`target_files`**
  - **Type:** Array of strings
  - **Description:** Names of files to create. If multiple target files are specified, the LLM requests are processed in parallel to increase speed.
  - **Example:** `["converter.py"]`

- **`model`** *(Optional)*
  - **Type:** String
  - **Description:** Specifies the LLM to use.
  - **Example:** `"gpt-4o"`

- **`instruction`**
  - **Type:** Multiline String with Macros
  - **Description:** Instructions provided to the LLM to guide the creation process. May contain the macro `{{filename}}` and any shared prompts.
  - **Example:**
    ```toml
    instruction = """
    Write a Python program {{filename}} that converts all JSON files in the directory into CSV files.
    {{error_handling}}
    {{commenting}}
    """
    ```

- **`context`**
  - **Type:** Array of strings
  - **Description:** Specifies files or items to include in the LLM context.
  - **Example:** `["*.json", "*.md"]`

**Example Command:**
```toml
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
```

##### B. LLM Edit Commands (`llm_edit`)

**Purpose:** Use a language model to edit existing files based on provided instructions and context. The output from the language model is used to modify the content of the files.

**Schema:**
```toml
[[commands]]
id = "<unique_command_id>"
type = "llm_edit"
target_files = ["<file_name1>", "<file_name2>", ...]
model = "<model_name>" # Optional: Uses defaults.model if omitted
instruction = """
<instruction_body with optional macros>
"""
context = ["<context_item1>", "<context_item2>", ...] # Optional
```

- **`target_files`**
  - **Type:** Array of strings
  - **Description:** Names of files to edit. If multiple target files are specified, the LLM requests are processed in parallel to increase speed.
  - **Example:** `["utils.py"]`

- **`model`** *(Optional)*
  - **Type:** String
  - **Description:** Specifies the LLM to use.
  - **Example:** `"gpt-4o"`

- **`model_prompt`** *(Optional)*
  - **Type:** String
  - **Description:** Specifies the LLM to use to rewrite prompts.
  - **Example:** `"gpt-4o"`

- **`instruction`**
  - **Type:** Multiline String with Macros
  - **Description:** Instructions provided to the LLM to guide the editing process. May contain placeholders like `{{filename}}` and any shared prompts. - **Example:**
    ```toml
    instruction = """
    Improve the function implementations in {{filename}} by optimizing performance and reducing memory usage.
    {{docstring_improvement}}
    """
    ```

- **`context`**
  - **Type:** Array of strings
  - **Description:** Specifies files or items to include in the LLM context. The contents of the edited file is always implicitly included as the first context item.
  - **Example:** `["*.py", "*.md", "{{filelist}}"]`

**Example Command:**
```toml
[[commands]]
id = "edit_utils"
type = "llm_edit"
target_files = ["utils.py"]
instruction = """
Improve the docstrings in {{filename}}.
{{docstring_improvement}}
"""
context = []
```

##### C. LLM Feedback-Edit Commands (`llm_feedback_edit`)

**Purpose:** Automate code correction by running one or more commands on a file, capturing any output (including errors), and using an LLM to fix those issues iteratively until the code executes successfully or a specified maximum number of retries is reached. When this command builds a chat prompt with the LLM. The first request, is the instruction + context, the second round is the instructions + context, then previous LLM's response, the instructions without the context. The LLM should see the history of the edits in its conversation history. The context should only be provided once in the first prompt.

**Schema:**
```toml
[[commands]]
id = "<unique_command_id>"
type = "llm_feedback_edit"
target_files = ["<file_name>"]
model = "<model_name>" # Optional: Uses defaults.model if omitted
test_commands = ["<test_command1>", "<test_command2>", ...]
max_retries = <number>
instruction = """
<instruction_body optional macros>
"""
context = ["<context_item1>", "<context_item2>", ...] # Optional
```

- **`target_files`**
  - **Type:** Array of strings
  - **Description:** Names of files to edit. If multiple target files are specified, the LLM requests are processed in parallel to increase speed.
  - **Example:** `["script.py"]`

- **`model`** *(Optional)*
  - **Type:** String
  - **Description:** Specifies the LLM to use.
  - **Example:** `"gpt-4o"`

- **`test_commands`**
  - **Type:** Array of strings
  - **Description:** Commands to execute that test the code. May include the `{{filename}}` placeholder. Error return codes from test_commands do not result in an error in the processing.
  - **Example:** `["python {{filename}}"]`

- **`max_retries`**
  - **Type:** Integer
  - **Description:** Maximum number of iterations to attempt fixing issues.
  - **Example:** `3`

- **`instruction`**
  - **Type:** Multiline String with optional Macros
  - **Description:** Instructions provided to the LLM to guide the error correction process. May also shared prompts  `{{macro_name}}`.
  - **Example:**
    ```toml
    instruction = """
    Please fix any errors in {{filename}} to make it run successfully.
    {{error_handling}}
    """
    ```

- **`context`**
  - **Type:** Array of strings
  - **Description:** Specifies files or items to include in the LLM context. The content of the file being edited is implicitly included as the first item in the context.
  - **Example:** `["*.py", "*.md"]`

**Example Command:**
```toml
[[commands]]
id = "feedback_edit_script"
type = "llm_feedback_edit"
target_files = ["script.py"]
instruction = """
The script {{filename}} failed to execute with the following output:
{{output}}
{{error_handling}}
Please fix any errors in {{filename}} to make it run successfully.
"""
test_commands = ["python {{filename}}"]
max_retries = 3
context = ["*.py", "*.md"]
```

## Context Handling

**Purpose:** Provide additional information to the LLM to improve output relevance. The context must always be provided.

**Context Items:**

- **File Patterns**: e.g., `*.py`, `docs/*.md` (patterns are resolved relative to the target directory).
- **Specific Files**: e.g., `utils.py`
- **Special Tokens (enclosed in curly braces):** e.g. {{filelist}}

**Example Usage in Commands:**
```toml
context = ["*.py", "*.md", "{{filelist}}"]
```

### 3. Macros
Instructions and contex can include these macro. 

**Built-in Macros:**
- **`{{filename}}`**: Automatically replaced with the current target file's name during command execution. Used in instructions and shell commands.
- **`{{output}}`**: In llm edit commands, replaced with the output from `test_commands`. It includes the command that was run, the return status code, stdout, and stdin. Text command that return an error do not result in the step erroring out.
- **`{{filelist}}`**: A generated list of files in the target directory with their sizes. The `log` directory and `__pycache__` directories are excluded.  If the file is binary the content of the file is included 40 bytes at a time
  first showing the ASCII version of the file, followed by the hex version of the 
  file. The program should include a built in list of binary file extensions.

### 3. Shared Prompts

**Purpose:** Define reusable prompt snippets that can be embedded within instruction texts. This allows for fine-grained reuse of common instruction components without requiring full prompt duplication.

**Guidelines for Custom Macros:**
- **Naming Conventions:** Use descriptive names in lowercase with underscores (e.g., `error_handling`).
- **Avoid Conflicts:** Do **not** define a shared prompt with the same name as any built-in macro (`file`, `filename`, `output`, `filelist`). Attempting to do so will result in a fatal error.
- **Placeholders within Macros:** Custom macros can include placeholders like `{{filename}}` or `{{output}}`, which will be substituted during execution.

```toml
[shared_prompts]
commenting = "Include proper comments explaining the code."
error_handling = "Ensure proper error handling is implemented."
docstring_improvement = "Enhance the docstrings to follow PEP 257 conventions."
```

- **`shared_prompts.<macro_name>`**
  - **Type:** String
  - **Description:** Defines a reusable prompt snippet identified by `<macro_name>`.
  - **Example:**
    ```toml
    [shared_prompts]
    commenting = "Include proper comments explaining the code."
    ```

**Referencing Shared Prompts in Instructions:**

Within the `instruction` field of commands, shared prompts can be included using the macro syntax `{{macro_name}}`. During processing, these macros will be replaced with their corresponding shared prompt content.

**Example:**
```toml
instruction = """
Write a Python program {{filename}} that converts all JSON files in the directory into CSV files.
{{error_handling}}
{{commenting}}
"""
```

**Supported Syntax for Macros:**
- **Inline Macros:** `{{macro_name}}` can be placed anywhere within the instruction text.
- **Multiple Instances:** The same macro can be used multiple times within an instruction. However, shared prompts can not include other shared prompts.

**Instruction Placeholder Resolution Process:**

1. **Identify Macros:** Scan the `instruction` text for `{{macro_name}}` patterns.
2. **Replace Shared Prompts:** Replace each `{{macro_name}}` with its corresponding shared prompt content defined in `[shared_prompts]`.
3. **Substitute Placeholders:** After shared pormpts are expanded, substitute built in macros like `{{filename}}`, `{{output}}`, etc., with their respective values based on the command context.
4. **Final Instruction:** The fully resolved instruction is then sent to the LLM.

**Example Resolution:**
Given the following shared prompt and command instruction:

```toml
[shared_prompts]
error_handling = "Ensure proper error handling is implemented."
commenting = "Include proper comments explaining the code."
```

```toml
instruction = """
Write a Python program {{filename}} that converts all JSON files in the directory into CSV files.
{{error_handling}}
{{commenting}}
"""
```

**Step-by-Step Resolution:**
1. Replace `{{error_handling}}` with "Ensure proper error handling is implemented."
2. Replace `{{commenting}}` with "Include proper comments explaining the code."
3. Replace `{{filename}}` with the target file's name (e.g., `converter.py`). filename should processed last in case it was included as part of a shared prompt.

**Final Instruction:**
```
Write a Python program converter.py that converts all JSON files in the directory into CSV files.
Ensure proper error handling is implemented.
Include proper comments explaining the code.
```

---

## Target Directive

```toml
[target]
directory = "output"
```

**Processing:**
- **`target.directory`**: Sets the working directory for generated files and outputs.
- The target directory will be created if it does not exist.
- **Behavior Based on Target Directory State:**
  - **Does Not Exist:** Create the directory and copy source files.
  - **Exists & Empty:** Copy source files.
  - **Exists & Not Empty:** 
    - **Default Behavior:** Do not copy source files.
- Log Directory*:* Create log directory under target director if it doesn't exist.
---

## Execution Flow

1. **Parse Command-Line Arguments:**
   - Obtain `instructions.toml` path.
   - `instructions.toml` is required; if not provided, an error is raised.

2. **Read Instruction File:**
   - Load and parse directives (`source`, `target`), defaults, shared prompts (macros), and commands.
   - Ensure command `id`s are unique.

3. **Validate Instruction File:**
   - **Schema Validation:** Ensure all required fields are present for each command type.
   - **Macro Validation:** Check for conflicts with built-in macros.
   - **Placeholder Validation:** Ensure all placeholders used are defined and can be resolved.
   - **Error Reporting:** Provide clear error messages indicating the nature and location of validation failures.

4. **Process Directives:**
   - **Target Directory Handling:**
     - Create if it does not exist.
     - If it exists and is empty, copy source files from `source.paths`.
     - If it exists and is not empty, handle based on configurable options (`overwrite`, `merge`).

5. **Execute Commands:**
   - **Order:** Commands are executed sequentially in the order they appear in the `commands` array.
   - **Command Types:**
     - **`llm_create`**:
       - Process each file in `target_files`.
       - Gather context and prepare the prompt for each file.
       - **Model Selection:**
         - Use the `model` specified in the command.
         - If `model` is not specified, use `defaults.model`.
       - **Instruction Resolution:**
         - Replace macros (`{{macro_name}}`) with their corresponding shared prompt snippets.
         - Substitute placeholders like `{{filename}}` with the current file's name.
       - Invoke the LLM API and handle the response.
       - Write outputs to files and logs.
     - **`llm_edit`**:
       - Process each file in `target_files`.
       - Gather context and prepare the prompt for each file.
       - **Model Selection:**
         - Use the `model` specified in the command.
         - If `model` is not specified, use `defaults.model`.
       - **Instruction Resolution:**
         - Replace macros (`{{macro_name}}`) with their corresponding shared prompt snippets.
         - Substitute placeholders like `{{filename}}` with the current file's name.
       - Invoke the LLM API and handle the response.
       - Update the files with the new content.
       - Log the operations.
     - **`llm_feedback_edit`**:
       - Process each file in `target_files`.
       - Gather context and prepare the prompt for each file.
       - **Model Selection:**
         - Use the `model` specified in the command.
         - If `model` is not specified, use `defaults.model`.
       - **Instruction Resolution:**
         - Replace macros (`{{macro_name}}`) with their corresponding shared prompt snippets.
         - Substitute placeholders like `{{filename}}` with the current file's name.
         - Ensure the `{{output}}` macro is present in the instruction.
       - Iteratively run test commands on a file, capture outputs, and use the LLM to fix issues.
       - Continue until the code executes successfully or the maximum number of retries is reached.
       - Log each iteration's details.

6. **Logging and Error Handling:**
   - Create a `log` subdirectory within the target directory if missing.
     - Each command creates a log file named `<command_id>.log`.
   - **LLM Commands:**
     - Additional logs for each file:
       - `<command_id>.<file_name>.llm-prompt.txt`: Contains the prompt sent to the LLM.
       - `<command_id>.<file_name>.llm-output.txt`: Contains the LLM's raw response.
   - **Error Handling:**
     - Commands fail gracefully with appropriate logging if errors occur.
   - **Validation Errors:**
     - If validation fails during the instruction file parsing, halt execution and log the errors.

7. **Output:**
   - Print to `stdout`:
     - Command start and completion times.
     - File processing statuses.
     - `OK` or `ERROR` at the end of each command, depending on success.
   - Detailed logs are available in the log files for review.

--- 
## LLM requests. 

The OpenAI API will be used to make the requests of the LLM.



---

## Error Handling and Logging

- **Error Handling:**
  - **Command Parsing:**
    - Ensure `id`s are unique.
    - Validate required fields for each command type.
    - Check for macro name conflicts with built-in macros.
  - **File Operations:**
    - Check for file existence and permissions.
    - Handle target directory state based on configurable options.
  - **LLM API Calls:**
    - Implement 3 retries on failures (e.g., network issues).
    - Raise an exception if the LLM API fails after retries.
  - **Validation Errors:**
    - Provide clear and descriptive error messages indicating the issue and its location within the instruction file.
    - Halt execution if critical validation errors are encountered.

- **Logging:**
  - At the start of the command, all existing logs with the same command ID should be deleted to ensure the logs always represent the latest execution.
  - **Log Directory:** `log` within the target directory.
  - **Log Files:**
    - `<command_id>.log`: Contains details of the command execution, including timestamps, prompts, responses, outputs, and errors.
    - `<command_id>.<file_name>.llm-prompt.txt`: Contains the prompt sent to the LLM.
    - `<command_id>.<file_name>.llm-output.txt`: Contains the LLM's raw response.
  - **LLM Feedback-Edit Commands:**
    - Log each iteration, including the retry count, prompt, response, and any outputs.
  - **Validation Logs:**
    - Separate log files for validation errors, if applicable.

- **Output:**
  - The program prints to `stdout`:
    - Command start and completion times.
    - File processing statuses.
    - `OK` or `ERROR` at the end of each command, depending on success.
  - All details are available in the log files for review.

---

## Validation Rules

To ensure the integrity and correctness of the instruction files and command executions, `llmbatchedit.py` enforces the following validation rules:

1. **Unique Command IDs:**
   - Each command must have a unique `id`.
   - Duplicate `id`s will result in a validation error.

2. **Required Fields:**
   - **General:**
     - Every command must include `id`, `type`, `target_files`, and `instruction`.
   - **Specific to Command Types:**
     - `llm_create`:
       - Must include `context`.
     - `llm_edit`:
       - `context` is optional but recommended.
     - `llm_feedback_edit`:
       - Must include `test_commands` and `max_retries`.
       - `instruction` must contain the `{{output}}` placeholder.

3. **Macro Name Conflicts:**
   - Custom macros defined in `[shared_prompts]` must not use names reserved for built-in macros (`filename`, `output`, `filelist`).
   - Attempting to redefine a built-in macro name will result in a fatal error.

4. **Placeholder Presence:**
   - All placeholders used within instructions and shared prompts must be defined and resolvable.
   - Missing placeholders will trigger a validation error.

5. **Model Specification:**
   - If a command specifies a `model`, it must be a supported LLM.
   - Unsupported models will result in a validation error.

7. **Command Parameters:**
   - **`max_retries`** must be a positive integer.
   - **`context`** and **`test_commands`** must be arrays of strings.
   - Invalid parameter types will result in a validation error.

8. **File Patterns:**
   - File patterns in `source.paths` and `context` must follow valid glob syntax.
   - Invalid patterns will trigger a validation error.

9. **Instruction Formatting:**
   - Instructions must be properly formatted multiline strings.
   - Missing or improperly closed multiline strings will result in a validation error.

10. **General TOML Syntax:**
    - The instruction file must adhere to correct TOML syntax.
    - Syntax errors will prevent the file from being parsed and will be reported.

**Error Reporting Mechanisms:**
- **Validation Errors:**
  - Clearly indicate the nature of the error (e.g., missing field, invalid value).
  - Specify the location within the instruction file (e.g., command `id`, specific line).
- **Execution Errors:**
  - Provide actionable feedback to resolve the issue.
  - Reference relevant log files for detailed information.

---

## Sample Instruction Files

### **Instructions with Macros and Enhanced `{{filename}}` Token (`sample-instructions.toml`)**

```toml

[target]
directory = "output"

[defaults]
model = "gpt-4o"

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
The script {{filename}} failed to execute with the following output:
{{output}}
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
{{output}}
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
{{output}}
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
merge = true

[defaults]
model = "gpt-4o"

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
context = ["*.cpp" ]

[[commands]]
id = "feedback_edit_cs_classes"
type = "llm_feedback_edit"
target_files = ["Class1.cs", "Class2.cs", "Utils.cs"]
instruction = """
The compilation of {{filename}} failed with the following errors:
{{output}}
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
{{output}}
{{fix_compilation_errors_cs}}
"""
test_commands = ["csc /target:library /out:ConvertedAssembly.dll {{filename}}"]
max_retries = 1
context = []
```
