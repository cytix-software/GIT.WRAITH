#!/usr/bin/env python3
import os
import sys
import ollama
import argparse
import re
from tree_sitter import Node
from tree_sitter_languages import get_parser, get_language
from pathspec import GitIgnoreSpec
from typing import Dict, List, Optional
import json
import traceback

MAX_TOKENS = 4096  # Adjust based on Mistral's context limit

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

def get_language_config(enable_langs: Optional[List[str]] = None,
                      disable_langs: Optional[List[str]] = None) -> Dict:
    """Return filtered language configuration"""
    enable_langs = enable_langs or []
    disable_langs = disable_langs or []

    if enable_langs:
        return {k: v for k, v in LANGUAGE_CONFIG.items() if k in enable_langs}
    return {k: v for k, v in LANGUAGE_CONFIG.items() if k not in disable_langs}

def generate_documentation(code, file_path):
    """Generate documentation using Ollama/Mistral"""
    prompt = (
        f"Generate documentation for this code file. "
        f"Start with a brief summary, then describe key components:\n\n{code}\n\nDocumentation:"
    )
    response = ollama.generate(model='mistral', prompt=prompt)
    return response['response']  # Changed from 'text' to 'response'

def analyze_business_logic_flaws(documentation, lang):
    """Analyze documentation to identify potential business logic flaws"""
    prompt = (
        f"Based on the documentation of a {lang} code file, identify potential business logic flaws. "
        f"List each flaw with a brief description using numbered list format:\n\n"
        f"Documentation:\n{documentation}\n\n"
        f"Potential flaws:\n"
    )
    try:
        response = ollama.generate(model='mistral', prompt=prompt)
        return response['response'].strip()
    except Exception as e:
        print(f"Error analyzing business logic flaws: {str(e)}")
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

    for line in lines:
        if re.match(section_regex, line.lstrip()):
            if current_section:
                sections.append(current_section)
            current_section = [line]
        else:
            current_section.append(line)
    if current_section:
        sections.append(current_section)

    total_tokens = sum(len(' '.join(sec).split()) for sec in sections)
    if total_tokens <= max_tokens:
        return '\n'.join(['\n'.join(sec) for sec in sections])

    kept_sections = []
    current_tokens = 0

    for sec in sections:
        sec_tokens = len(' '.join(sec).split())
        if current_tokens + sec_tokens > max_tokens:
            break
        kept_sections.append(sec)
        current_tokens += sec_tokens

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

def process_repository(repo_path: str, config: Dict, max_tokens: int):
    """Process all code files in the repository while respecting .gitignore"""
    summaries = []
    flaws_list = []  # New list to collect flaws
    spec = get_gitignore_spec(repo_path)

    for root, dirs, files in os.walk(repo_path, topdown=True):
        # Check if current directory is ignored (handle directory patterns with/without trailing slash)
        rel_dir = os.path.relpath(root, repo_path).replace('\\', '/')
        if spec:
            dir_ignored = spec.match_file(rel_dir) or spec.match_file(f"{rel_dir}/")
            if dir_ignored:
                dirs[:] = []  # Skip subdirectories
                continue  # Skip processing files in this directory

        # Filter files using .gitignore
        filtered_files = []
        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, repo_path).replace('\\', '/')

            # Skip ignored files
            if spec and spec.match_file(rel_path):
                continue

            filtered_files.append(file)

        # Process remaining files
        for file in filtered_files:
            ext = os.path.splitext(file)[1].lower()
            lang = next((k for k, v in config.items() if ext in v['extensions']), None)
            file_path = os.path.join(root, file)
            #lang, config = get_language_config(file_path)

            if not lang:
                continue  # Skip unsupported file types

            print(f"Processing: {file_path}")

            # Read and truncate code
            try:
                with open(file_path, 'r') as f:
                    original_code = f.read()

                section_regex = config[lang]['section_regex']
                truncated_code = truncate_code(original_code, max_tokens, section_regex)
            except Exception as e:
                print(f"Error reading {file_path}: {str(e)}")
                traceback.print_exc()
                continue

            # Generate documentation
            try:
                doc = generate_documentation(truncated_code, file_path)
            except Exception as e:
                print(f"Documentation generation failed for {file_path}: {str(e)}")
                continue

            # Analyze for business logic flaws
            try:
                flaws = analyze_business_logic_flaws(doc, lang)
                if flaws.strip():
                    flaws_list.append((file_path, flaws))
            except Exception as e:
                print(f"Flaw analysis failed for {file_path}: {str(e)}")

            # Save documentation
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

            # Extract summary (first paragraph)
            summary = doc.split('\n\n')[0] if '\n\n' in doc else doc.split('\n')[0]
            summaries.append((file_path, summary))

    # Generate top-level summary
    try:
        summary_path = os.path.join(repo_path, 'summary.docs.md')
        with open(summary_path, 'w') as f:
            f.write("# Repository Overview\n\n")
            for path, summary in summaries:
                rel_path = os.path.relpath(path, repo_path).replace('\\', '/')
                f.write(f"- **{rel_path}**: {summary}\n")
    except Exception as e:
        print(f"Error creating summary: {str(e)}")

    # Generate business logic flaws report
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
    parser = argparse.ArgumentParser(description='Repository Code Processor')
    parser.add_argument('repo_path', type=str, help='Path to the repository')
    parser.add_argument('--max-tokens', type=int, default=8000)
    parser.add_argument('--config-file', type=str)
    parser.add_argument('--enable-languages', type=str)
    parser.add_argument('--disable-languages', type=str)
    args = parser.parse_args()

    # Load configuration
    config = {}
    if args.config_file:
        try:
            with open(args.config_file, 'r') as f:
                content = f.read().strip()
                # Load JSON content, handle empty files, and ensure config is a dictionary
                config = json.loads(content) if content else {}
                config = config or {}  # Fallback to empty dict if loaded value is falsy
        except Exception as e:
            print(f"Error loading config file: {e}")
            return

    # Determine language configuration
    enable_langs = args.enable_languages.split(',') if args.enable_languages else config.get('enable_languages', [])
    disable_langs = args.disable_languages.split(',') if args.disable_languages else config.get('disable_languages', [])

    language_config = get_language_config(enable_langs, disable_langs)

    # Process repository
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
