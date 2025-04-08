#!/usr/bin/env python3
import os
import sys
import boto3
import argparse
import re
from tree_sitter import Node
from tree_sitter_languages import get_parser, get_language
from pathspec import GitIgnoreSpec
from typing import Dict, List, Optional
import json
import traceback

# Initialize Bedrock client for AI model access
bedrock = boto3.client('bedrock-runtime', region_name='eu-west-2')

# Maximum tokens allowed for code analysis
MAX_TOKENS = 4096

# Configuration for different programming languages
# Each language specifies:
# - File extensions
# - Comment pattern regex
# - Section/block pattern regex (functions, classes etc)
LANGUAGE_CONFIG = {
    'python': {
        'extensions': ['.py'],
        'comment_regex': r'^\s*#',
        'section_regex': r'^\s*(def|class|async def)\b'
    },
    'javascript': {
        'extensions': ['.js', '.jsx', '.ts', '.tsx'],
        'comment_regex': r'^\s*//|^\s*/\*',
        'section_regex': r'^\s*(function|class|export\s+\w+)\b'
    },
    'java': {
        'extensions': ['.java'],
        'comment_regex': r'^\s*//|^\s*/\*',
        'section_regex': r'^\s*(public|private|protected|static)?\s*(class|interface|enum)\b'
    },
    'go': {
        'extensions': ['.go'],
        'comment_regex': r'^\s*//',
        'section_regex': r'^\s*(func|type)\b'
    },
    'cpp': {
        'extensions': ['.cpp', '.hpp', '.cxx', '.hxx'],
        'comment_regex': r'^\s*//|^\s*/\*',
        'section_regex': r'^\s*(class|struct|enum|template|namespace)\b'
    },
    'csharp': {
        'extensions': ['.cs'],
        'comment_regex': r'^\s*//|^\s*/\*',
        'section_regex': r'^\s*(public|private|protected|internal)?\s*(class|struct|enum|namespace)\b'
    },
    'ruby': {
        'extensions': ['.rb'],
        'comment_regex': r'^\s*#',
        'section_regex': r'^\s*(def|class|module)\b'
    },
    'php': {
        'extensions': ['.php'],
        'comment_regex': r'^\s*//|^\s*#\s*|^\s*/\*',
        'section_regex': r'^\s*(function|class|trait)\b'
    },
    'rust': {
        'extensions': ['.rs'],
        'comment_regex': r'^\s*//',
        'section_regex': r'^\s*(fn|struct|enum|impl|trait)\b'
    },
    'swift': {
        'extensions': ['.swift'],
        'comment_regex': r'^\s*//',
        'section_regex': r'^\s*(func|class|struct|enum)\b'
    },
    'kotlin': {
        'extensions': ['.kt'],
        'comment_regex': r'^\s*//|^\s*/\*',
        'section_regex': r'^\s*(fun|class|object|interface)\b'
    },
    'bash': {
        'extensions': ['.sh'],
        'comment_regex': r'^\s*#',
        'section_regex': r'^\s*(function)\b'
    }
}

def bedrock_generate(prompt: str, model_id='mistral.mixtral-8x7b-instruct-v0:1') -> str:
    """Generate text using AWS Bedrock AI model"""
    body = {
        "prompt": f"<s>[INST] {prompt} [/INST]",
        "temperature": 0.5,
        "top_k": 50,
        "top_p": 0.9
    }

    response = bedrock.invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        contentType='application/json',
        accept='application/json'
    )

    try:
        raw = response['body'].read().decode('utf-8')
        data = json.loads(raw)
        print(json.dumps(data, indent=2))
        return data['outputs'][0]['text'].strip()
    except Exception as e:
        print("Error parsing Bedrock response:", str(e))
        return ""

def get_language_config(enable_langs: Optional[List[str]] = None,
                      disable_langs: Optional[List[str]] = None) -> Dict:
    """Return filtered language configuration"""
    enable_langs = enable_langs or []
    disable_langs = disable_langs or []

    if enable_langs:
        return {k: v for k, v in LANGUAGE_CONFIG.items() if k in enable_langs}
    return {k: v for k, v in LANGUAGE_CONFIG.items() if k not in disable_langs}

# Generates comprehensive documentation for a given code file using AWS Bedrock AI.
# The documentation includes a brief summary, description of key components,
# and overview of important classes, functions, and their relationships.
# Input: code (str) - source code to document, file_path (str) - path to source file
# Output: str - generated documentation in markdown format
def generate_documentation(code, file_path):
    """Generate documentation using Bedrock"""
    prompt = (
        f"<s>[INST] You are an expert software engineer and technical writer. "
        f"Your task is to analyze the following code and generate comprehensive documentation.\n\n"
        f"Code:\n{code}\n\n"
        f"Please provide:\n"
        f"1. A high-level overview of the code's purpose and functionality\n"
        f"2. Detailed description of key components, classes, and functions\n"
        f"3. Explanation of important algorithms, data structures, or patterns used\n"
        f"4. Any security considerations or potential vulnerabilities\n"
        f"5. Dependencies and integration points with other systems\n\n"
        f"Format your response in clear, well-structured markdown. "
        f"Use appropriate headings, code blocks, and bullet points for readability. "
        f"Focus on making the documentation useful for both developers and security engineers.\n\n"
        f"Documentation: [/INST]"
    )
    return bedrock_generate(prompt)

# Analyzes code documentation to identify potential business logic issues and vulnerabilities.
# Identifies issues like inconsistent error handling, missing edge cases,
# potential race conditions, security vulnerabilities, and business rule violations.
# Input: documentation (str) - documentation to analyze, lang (str) - programming language
# Output: str - numbered list of identified potential flaws with descriptions
def generate_threat_model(documentation, lang):
    """Generate a comprehensive application security threat model based on code documentation"""
    prompt = (
        f"<s>[INST] You are an expert application security penetration tester and threat modeler. "
        f"Based on the following documentation for a {lang} codebase, create a detailed application security threat model "
        f"from an attacker's perspective.\n\n"
        f"Documentation:\n{documentation}\n\n"
        f"Create an application security focused threat model following these guidelines:\n\n"
        f"1. Application Overview:\n"
        f"   - Key application functionality and features\n"
        f"   - User roles and privilege levels\n"
        f"   - Authentication and authorization mechanisms\n"
        f"   - Data processing flows\n"
        f"   - External integrations and APIs\n\n"
        f"2. Attack Surface Analysis:\n"
        f"   - User input points (forms, APIs, file uploads)\n"
        f"   - Session management mechanisms\n"
        f"   - State transitions and business workflows\n"
        f"   - Data storage and retrieval points\n"
        f"   - Integration points with external systems\n\n"
        f"3. Attack Scenarios:\n"
        f"   IMPORTANT: Only identify attack scenarios where there is clear evidence in the documentation.\n"
        f"   Focus on how an attacker could exploit the application's functionality.\n"
        f"   For each identified attack scenario, provide:\n"
        f"   - Specific application functionality that could be exploited\n"
        f"   - Step-by-step attack path from an attacker's perspective\n"
        f"   - Required attacker position (authenticated/unauthenticated)\n"
        f"   - Technical prerequisites for the attack\n"
        f"   - Potential impact on the application or its users\n\n"
        f"4. Security Weaknesses:\n"
        f"   - Document exploitable application behaviors\n"
        f"   - Identify security mechanism bypasses\n"
        f"   - Note any insufficient validation or sanitization\n"
        f"   - Point out trust assumptions that could be violated\n\n"
        f"5. Attack Testing Guide:\n"
        f"   - Specific payloads or techniques to test each attack scenario\n"
        f"   - Tools useful for exploiting identified weaknesses\n"
        f"   - Custom scripts or modifications needed\n"
        f"   - Tips for bypassing existing security controls\n\n"
        f"6. Impact Assessment:\n"
        f"   - Exploitability rating for each attack scenario\n"
        f"   - Potential business and user impact\n"
        f"   - Attack complexity assessment\n"
        f"   - Detection likelihood\n\n"
        f"Format your response in clear, well-structured markdown. "
        f"Make the threat model practical for security testers to use as an attack guide.\n"
        f"IMPORTANT: Focus only on realistic application security threats that an attacker could exploit.\n"
        f"Base all attack scenarios on actual application functionality evident in the documentation.\n\n"
        f"Application Security Threat Model: [/INST]"
    )
    try:
        return bedrock_generate(prompt)
    except Exception as e:
        print(f"Error generating application security threat model: {str(e)}")
        return ""

def get_gitignore_spec(repo_path):
    """Load .gitignore patterns into a GitIgnoreSpec"""
    gitignore_path = os.path.join(repo_path, '.gitignore')
    if os.path.exists(gitignore_path):
        with open(gitignore_path, 'r') as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith('#')] + ['.git/']
            return GitIgnoreSpec.from_lines(lines)
    return None

def truncate_code(code: str, max_tokens: int, section_regex: str) -> str:
    """Intelligent truncation preserving code structure"""
    lines = code.split('\n')
    sections = []
    current_section = []

    # Group code into logical sections based on regex pattern
    for line in lines:
        if re.match(section_regex, line.lstrip()):
            if current_section:
                sections.append(current_section)
            current_section = [line]
        else:
            current_section.append(line)
    if current_section:
        sections.append(current_section)

    # Check if truncation is needed
    total_tokens = sum(len(' '.join(sec).split()) for sec in sections)
    if total_tokens <= max_tokens:
        return '\n'.join(['\n'.join(sec) for sec in sections])

    # Truncate while preserving complete sections where possible
    kept_sections = []
    current_tokens = 0

    for sec in sections:
        sec_tokens = len(' '.join(sec).split())
        if current_tokens + sec_tokens > max_tokens:
            break
        kept_sections.append(sec)
        current_tokens += sec_tokens

    # Try to include partial sections with remaining tokens
    if current_tokens < max_tokens:
        remaining = max_tokens - current_tokens
        for line in sections[len(kept_sections)]:
            line_tokens = len(line.split())
            if remaining - line_tokens >= 0:
                kept_sections.append([line])
                remaining -= line_tokens
            else:
                break

    return '\n'.join(['\n'.join(sec) for sec in kept_sections])

def should_ignore_file(file_path: str) -> bool:
    """
    Determines if a file should be ignored based on common patterns for installation
    and third-party files.
    
    Args:
        file_path (str): The path to the file to check
        
    Returns:
        bool: True if the file should be ignored, False otherwise
    """
    # Common installation and setup files
    setup_files = {
        'setup.py', 'setup.cfg', 'setup.sh', 'install.sh', 'requirements.txt',
        'Pipfile', 'Pipfile.lock', 'package.json', 'package-lock.json',
        'yarn.lock', 'composer.json', 'composer.lock', 'Gemfile', 'Gemfile.lock'
    }
    
    # Common virtual environment and dependency directories
    venv_dirs = {
        'venv', '.venv', 'env', '.env', 'node_modules', 'vendor',
        '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache'
    }
    
    # Get the filename and directory components
    filename = os.path.basename(file_path)
    dir_parts = file_path.split(os.sep)
    
    # Check if it's a setup file
    if filename in setup_files:
        return True
        
    # Check if it's in a virtual environment or dependency directory
    if any(venv_dir in dir_parts for venv_dir in venv_dirs):
        return True
        
    # Check for common build and distribution directories
    if 'dist' in dir_parts or 'build' in dir_parts:
        return True
        
    # Check for common IDE and editor files
    if filename.startswith('.') and filename not in ['.gitignore', '.env.example']:
        return True
        
    return False

def process_repository(repo_path: str, config: Dict, max_tokens: int):
    """Process all code files in the repository while respecting .gitignore"""
    summaries = []
    flaws_list = []  # List to collect identified flaws
    spec = get_gitignore_spec(repo_path)

    for root, dirs, files in os.walk(repo_path, topdown=True):
        # Skip ignored directories
        rel_dir = os.path.relpath(root, repo_path).replace('\\', '/')
        if spec:
            dir_ignored = spec.match_file(rel_dir) or spec.match_file(f"{rel_dir}/")
            if dir_ignored:
                dirs[:] = []  # Skip subdirectories
                continue  # Skip processing files in this directory

        # Filter out ignored files
        filtered_files = []
        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, repo_path).replace('\\', '/')

            # Skip files based on .gitignore
            if spec and spec.match_file(rel_path):
                continue
                
            # Skip common installation and third-party files
            if should_ignore_file(rel_path):
                continue

            filtered_files.append(file)

        # Process each valid file
        for file in filtered_files:
            ext = os.path.splitext(file)[1].lower()
            lang = next((k for k, v in config.items() if ext in v['extensions']), None)
            file_path = os.path.join(root, file)

            if not lang:
                continue  # Skip unsupported file types

            print(f"Processing: {file_path}")

            # Read and truncate code to fit token limit
            try:
                with open(file_path, 'r') as f:
                    original_code = f.read()

                section_regex = config[lang]['section_regex']
                truncated_code = truncate_code(original_code, max_tokens, section_regex)
            except Exception as e:
                print(f"Error reading {file_path}: {str(e)}")
                traceback.print_exc()
                continue

            # Generate documentation using AI
            try:
                doc = generate_documentation(truncated_code, file_path)
            except Exception as e:
                print(f"Documentation generation failed for {file_path}: {str(e)}")
                continue

            # Analyze code for potential business logic issues
            try:
                flaws = generate_threat_model(doc, lang)
                if flaws.strip():
                    flaws_list.append((file_path, flaws))
            except Exception as e:
                print(f"Threat model generation failed for {file_path}: {str(e)}")

            # Save generated documentation
            try:
                doc_dir = os.path.dirname(file_path)
                doc_filename = os.path.basename(file_path) + '.docs.md'
                doc_path = os.path.join(doc_dir, doc_filename)

                with open(doc_path, 'w') as f:
                    f.write(f"# {lang.capitalize()} Code Documentation\n")
                    f.write(doc)
            except Exception as e:
                print(f"Error saving documentation for {file_path}: {str(e)}")
                continue

            # Extract summary for repository overview
            summary = doc.split('\n\n')[0] if '\n\n' in doc else doc.split('\n')[0]
            summaries.append((file_path, summary))

    # Generate repository-wide summary document
    try:
        summary_path = os.path.join(repo_path, 'summary.docs.md')
        with open(summary_path, 'w') as f:
            f.write("# Repository Overview\n\n")
            for path, summary in summaries:
                rel_path = os.path.relpath(path, repo_path).replace('\\', '/')
                f.write(f"- **{rel_path}**: {summary}\n")
    except Exception as e:
        print(f"Error creating summary: {str(e)}")

    # Generate business logic analysis report
    flaws_report_path = os.path.join(repo_path, 'logic-flaws.analysis.md')
    try:
        with open(flaws_report_path, 'w') as f:
            for file_path, flaws in flaws_list:
                rel_path = os.path.relpath(file_path, repo_path).replace('\\', '/')
                f.write(f"File: {rel_path}\n")
                f.write("Potential Business Logic Flaws:\n")
                f.write(flaws)
                f.write("\n" + "="*40 + "\n")
    except Exception as e:
        print(f"Error creating business logic flaws report: {str(e)}")

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Repository Code Processor')
    parser.add_argument('repo_path', type=str, help='Path to the repository')
    parser.add_argument('--max-tokens', type=int, default=8000)
    parser.add_argument('--config-file', type=str)
    parser.add_argument('--enable-languages', type=str)
    parser.add_argument('--disable-languages', type=str)
    args = parser.parse_args()

    # Load custom configuration if provided
    config = {}
    if args.config_file:
        try:
            with open(args.config_file, 'r') as f:
                content = f.read().strip()
                config = json.loads(content) if content else {}
                config = config or {}  # Fallback to empty dict if loaded value is false
        except Exception as e:
            print(f"Error loading config file: {e}")
            return

    # Set up language processing configuration
    enable_langs = args.enable_languages.split(',') if args.enable_languages else config.get('enable_languages', [])
    disable_langs = args.disable_languages.split(',') if args.disable_languages else config.get('disable_languages', [])

    language_config = get_language_config(enable_langs, disable_langs)

    # Process the repository
    try:
        result = process_repository(
            args.repo_path,
            language_config,
            args.max_tokens
        )
        print(result)
    except Exception as e:
        print(f"Processing failed: {e}")
        traceback.print_exc()


if __name__ == '__main__':
    main()
