#!/usr/bin/env python3
import os
import sys
import ollama
from tree_sitter import Node
from tree_sitter_languages import get_parser, get_language
from pathspec import GitIgnoreSpec

MAX_TOKENS = 4096  # Adjust based on Mistral's context limit

LANGUAGE_CONFIG = {
    'python': {
        'extensions': ['.py'],
        'function_nodes': ['function_definition'],
        'class_nodes': ['class_definition'],
        'body_node_type': 'block',
        'comment_syntax': '#'
    },
    'javascript': {
        'extensions': ['.js', '.jsx'],
        'function_nodes': ['function_declaration', 'method_definition'],
        'class_nodes': ['class_declaration'],
        'body_node_type': 'statement_block',
        'comment_syntax': '//'
    },
    'typescript': {
        'extensions': ['.ts', '.tsx'],
        'function_nodes': ['function_declaration', 'method_signature', 'method_definition'],
        'class_nodes': ['class_declaration', 'interface_declaration'],
        'body_node_type': 'statement_block',
        'comment_syntax': '//'
    },
    'vue': {
        'extensions': ['.vue'],
        'function_nodes': ['function_declaration', 'method_definition'],
        'class_nodes': ['class_declaration'],
        'body_node_type': 'statement_block',
        'comment_syntax': '//',
        'script_tag': 'script_element'  # Special handling for Vue SFCs
    },
    'java': {
        'extensions': ['.java'],
        'function_nodes': ['method_declaration'],
        'class_nodes': ['class_declaration'],
        'body_node_type': 'block',
        'comment_syntax': '//'
    },
    'c': {
        'extensions': ['.c', '.h'],
        'function_nodes': ['function_definition'],
        'body_node_type': 'compound_statement',
        'comment_syntax': '//'
    },
    'cpp': {
        'extensions': ['.cpp', '.hpp', '.cxx'],
        'function_nodes': ['function_definition'],
        'class_nodes': ['class_specifier'],
        'body_node_type': 'compound_statement',
        'comment_syntax': '//'
    },
    'ruby': {
        'extensions': ['.rb'],
        'function_nodes': ['method'],
        'class_nodes': ['class'],
        'body_node_type': 'body_statement',
        'comment_syntax': '#'
    },
    'go': {
        'extensions': ['.go'],
        'function_nodes': ['function_declaration'],
        'body_node_type': 'block',
        'comment_syntax': '//'
    }
}

def get_language_config(file_path):
    """Determine language configuration based on file extension"""
    ext = os.path.splitext(file_path)[1].lower()
    for lang, cfg in LANGUAGE_CONFIG.items():
        if ext in cfg.get('extensions', []):
            return lang, cfg
    return None, None

def truncate_code(code, file_path):
    """Truncate code by removing function/class bodies if too long"""
    tokens = len(code.split())
    if tokens <= MAX_TOKENS:
        return code

    lang, config = get_language_config(file_path)
    if not lang:
        return code  # Unsupported language, return original

    try:
        parser = get_parser(lang)
        tree = parser.parse(bytes(code, 'utf-8'))
        root_node = tree.root_node
        replacements = []
        placeholder = f"\n{config['comment_syntax']} ... content truncated ...\n".encode()

        # Special handling for Vue Single File Components
        if lang == 'vue':
            script_nodes = []
            def find_script_nodes(node):
                if node.type == config.get('script_tag', 'script_element'):
                    script_nodes.append(node)
                for child in node.children:
                    find_script_nodes(child)
            find_script_nodes(root_node)
            # Only process code inside script tags
            if script_nodes:
                root_node = script_nodes[0]

        def walk(node):
            if node.type in config.get('function_nodes', []) + config.get('class_nodes', []):
                body_node = None
                for child in node.children:
                    if child.type == config['body_node_type']:
                        body_node = child
                        break
                if body_node:
                    replacements.append((body_node.start_byte, body_node.end_byte))
            for child in node.children:
                walk(child)

        walk(root_node)

        # Sort in reverse order to handle nested functions
        replacements.sort(reverse=True, key=lambda x: x[0])

        code_bytes = bytearray(code.encode('utf-8'))
        for start, end in replacements:
            code_bytes[start:end] = placeholder

        truncated_code = code_bytes.decode('utf-8')
        return truncated_code if len(truncated_code.split()) <= MAX_TOKENS else code
    except Exception as e:
        print(f"Truncation error for {file_path}: {str(e)}")
        return code  # Return original on parsing error

# In generate_documentation function:
def generate_documentation(code, file_path):
    """Generate documentation using Ollama/Mistral"""
    lang, _ = get_language_config(file_path)
    prompt = (
        f"Generate documentation for this {lang} code file. "
        f"Start with a brief summary, then describe components:\n\n{code}\n\nDocumentation:"
    )
    response = ollama.generate(model='mistral', prompt=prompt)
    return response['response']  # Changed from 'text' to 'response'

def get_gitignore_spec(repo_path):
    """Load .gitignore patterns into a GitIgnoreSpec"""
    gitignore_path = os.path.join(repo_path, '.gitignore')
    if os.path.exists(gitignore_path):
        with open(gitignore_path, 'r') as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith('#')] + ['.git/']
            return GitIgnoreSpec.from_lines(lines)
    return None

def process_repository(repo_path):
    """Process all code files in the repository while respecting .gitignore"""
    summaries = []
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
            file_path = os.path.join(root, file)
            lang, _ = get_language_config(file_path)

            if not lang:
                continue  # Skip unsupported file types

            print(f"Processing: {file_path}")

            # Read and truncate code
            try:
                with open(file_path, 'r') as f:
                    original_code = f.read()
                truncated_code = truncate_code(original_code, file_path)
            except Exception as e:
                print(f"Error reading {file_path}: {str(e)}")
                continue

            # Generate documentation
            try:
                doc = generate_documentation(truncated_code, file_path)
            except Exception as e:
                print(f"Documentation generation failed for {file_path}: {str(e)}")
                continue

            # Save documentation
            try:
                doc_dir = os.path.dirname(file_path)
                doc_filename = os.path.splitext(os.path.basename(file_path))[0] + '.docs.md'
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

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: gitwraith <repository_path>")
        sys.exit(1)

    repo_path = sys.argv[1]
    if not os.path.isdir(repo_path):
        print(f"Error: {repo_path} is not a valid directory")
        sys.exit(1)

    process_repository(repo_path)
