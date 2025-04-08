# Python Code Documentation
# Comprehensive Documentation Generator

This script is designed to analyze source code and generate comprehensive documentation using the AWS Bedrock AI model. It supports multiple programming languages and can identify potential business logic issues and vulnerabilities.

## Features

- Generates documentation for various programming languages, including Python, JavaScript, Java, Go, C++, C#, Ruby, PHP, Rust, Swift, and Kotlin.
- Truncates code while preserving structure to fit within the maximum token limit for AI analysis.
- Analyzes code documentation to identify potential business logic issues and vulnerabilities.
- Generates a threat model based on the code documentation from an attacker's perspective.
- Ignores common installation and third-party files while processing the repository.
- Saves generated documentation in markdown format for each file and a summary document for the entire repository.
- Generates a report of potential business logic flaws based on the analyzed code.

## Usage

To use this script, simply run it with the path to the repository and optional configuration parameters:

```bash
python3 doc_generator.py /path/to/repository --max-tokens 8000 --config-file config.json
```

Replace `/path/to/repository` with the actual path to your repository. The `--max-tokens` parameter specifies the maximum number of tokens allowed for code analysis. The `--config-file` parameter is optional and allows you to provide a custom configuration file.

## Configuration

The configuration file (`config.json`) is a JSON file that can include the following parameters:

```json
{
  "enable_languages": ["python", "javascript"],
  "disable_languages": ["java", "csharp"]
}
```

The `enable_languages` and `disable_languages` parameters allow you to specify the programming languages to be processed. By default, all supported languages are processed.

## Supported Languages

The following programming languages are supported:

- Python
- JavaScript (including JSX, TypeScript, and TSX)
- Java
- Go
- C++ (including CPP and HPP)
- C#
- Ruby
- PHP
- Rust
- Swift
- Kotlin