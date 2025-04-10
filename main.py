#!venv/bin/python
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
import hashlib
import bottle
from server import *
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from tqdm import tqdm
import random
from botocore.exceptions import ClientError
import math

# Initialize Bedrock client for AI model access
bedrock = boto3.client('bedrock-runtime', region_name='eu-west-2')

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

def compute_file_hash(filepath, algorithm='sha256', max_size=10 * 1024 * 1024, sample_size=64 * 1024):
    """
    Computes the hash of a file. If the file is larger than max_size,
    only a sample from the beginning and end of the file is used.

    Args:
        filepath (str): Path to the file.
        algorithm (str): Hash algorithm (default 'sha256').
        max_size (int): Threshold size (in bytes) above which only a sample is hashed.
        sample_size (int): Number of bytes to read from start and end for large files.

    Returns:
        str: Hexadecimal digest of the hash.
    """
    try:
        hasher = hashlib.new(algorithm)
    except ValueError:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")

    file_size = os.path.getsize(filepath)

    with open(filepath, 'rb') as f:
        # For small files, hash the entire content.
        if file_size <= max_size:
            while True:
                chunk = f.read(4096)
                if not chunk:
                    break
                hasher.update(chunk)
        else:
            # For large files, hash only a sample: beginning, file size, and end.
            # Read beginning
            beginning = f.read(sample_size)
            hasher.update(beginning)

            # Include the file size to help differentiate files with similar samples.
            hasher.update(str(file_size).encode('utf-8'))

            # Read end sample: seek to the last sample_size bytes
            if file_size > sample_size:
                f.seek(-sample_size, os.SEEK_END)
                end_sample = f.read(sample_size)
                hasher.update(end_sample)

    return hasher.hexdigest()

def compute_cache(repo_path, file_list, json_hashes_path, algorithm='sha256',
                                 max_size=10 * 1024 * 1024, sample_size=64 * 1024):
    """
    Checks a list of files against a stored JSON of hashes. Returns only those files
    that are new or whose content has changed. If the stored hash file is missing or empty,
    it returns all files. The new hash values are saved to the JSON file.

    Args:
        file_list (list of str): List of file paths to check.
        json_hashes_path (str): Path to the JSON file storing file hashes.
        algorithm (str): Hashing algorithm (default 'sha256').
        max_size (int): File size threshold for partial hashing.
        sample_size (int): Sample size in bytes for hashing large files.

    Returns:
        list of str: Files that have changed or are not present in the stored hashes.
    """
    # Load previous hashes if available
    try:
        with open(json_hashes_path, 'r') as f:
            stored_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        stored_cache = {'hashes': {}, 'summaries': {}}

    # Ensure stored_cache has the required structure
    if 'hashes' not in stored_cache:
        stored_cache['hashes'] = {}
    if 'summaries' not in stored_cache:
        stored_cache['summaries'] = {}

    # Determine if we should consider all files changed
    full_run = not stored_cache or not stored_cache['hashes'] or len(stored_cache['hashes']) == 0

    new_cache = {'hashes': {}, 'summaries': {}}
    changed_files = []

    for filepath in file_list:
        full_path = os.path.join(repo_path, filepath)
        if not os.path.isfile(full_path):
            continue

        new_hash = compute_file_hash(full_path, algorithm=algorithm,
                                     max_size=max_size, sample_size=sample_size)
        new_cache['hashes'][filepath] = new_hash
        # If a full run (no previous hashes) or if the file is new/changed, add to changed list.
        if full_run or stored_cache['hashes'].get(filepath) != new_hash:
            changed_files.append(filepath)

    return changed_files, new_cache

import time
import random
import json
from botocore.exceptions import ClientError

def bedrock_generate(prompt: str, model_id='anthropic.claude-3-sonnet-20240229-v1:0') -> str:
    """Generate text using AWS Bedrock AI model with exponential backoff for ThrottlingExceptions"""
    #estimate the number of tokens needed
    max_tokens = 2**math.ceil(math.log(len(prompt)/3, 2))

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0,
        "top_k": 1,
        "top_p": 1.0
    }

    max_retries = 10
    initial_delay = 1.0  # seconds
    backoff_factor = 2
    jitter = 0.1  # 10% jitter

    for attempt in range(max_retries + 1):
        try:
            response = bedrock.invoke_model(
                modelId=model_id,
                body=json.dumps(body),
                contentType='application/json',
                accept='application/json'
            )

            try:
                raw = response['body'].read().decode('utf-8')
                data = json.loads(raw)
                if data['stop_reason'] == 'max_tokens':
                    tqdm.write(f"Warning: Output truncated, max tokens reached {max_tokens}")
                return data['content'][0]['text'].strip()
            except Exception as e:
                tqdm.write("Error parsing Bedrock response:", str(e))
                return ""

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ThrottlingException' and attempt < max_retries:
                tqdm.write(f"Error invoking Bedrock model. Attempt: {attempt}, Error: {error_code} {str(e)}; Retrying...")
                # Calculate delay with exponential backoff and jitter
                delay = initial_delay * (backoff_factor ** attempt)
                delay *= random.uniform(1 - jitter, 1 + jitter)
                time.sleep(delay)
                continue
            else:
                tqdm.write(f"Error invoking Bedrock model. Attempt: {attempt}, Error: {error_code} {str(e)}")
                # Re-raise the exception if it's not a ThrottlingException or retries are exhausted
                return ""
        except Exception as e:
            # Handle any other exceptions that occur during the API call
            tqdm.write(f"Unexpected error: {str(e)}")
            traceback.print_exc()

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
        f"<s><instructions>\nYou are an expert software engineer and technical writer. "
        f"Your task is to analyze this file and generate concise but technically detailed documentation.\n\n"
        f"Please provide:\n"
        f"1. A single-sentence overview of the file's purpose\n"
        f"2. Key technical components (classes, functions, data structures) with their specific purposes\n"
        f"3. Critical algorithms, patterns, or technical implementations\n"
        f"4. Security considerations specific to the code's functionality\n"
        f"5. Core dependencies and integration points (ignore third-party library details)\n\n"
        f"Format your response in clear, concise markdown. "
        f"Focus on technical implementation details and avoid verbose descriptions. "
        f"Reference code elements by their exact names from the file.\n"
        f"Keep each section brief but information-dense.\n</instructions>\n\n"
        f"<code>\n{code}</code>\n\n"
        f"Documentation:"
    )
    return bedrock_generate(prompt)

def generate_summary(documentation, file_path):
    """Generate a summary of the documentation"""
    prompt = (
        f"<s><instructions>You are an expert software engineer and technical writer. "
        f"Your task is to analyze this file and generate a concise summary, up to 3 sentences long. Refer to the code by either its name '{os.path.basename(file_path)}' or a classname or function name found in the file.''\n\n"
        f"</instructions>\n"
        f"<file>\n{documentation}\n</file>\n"
        f"Summary:"
    )
    return bedrock_generate(prompt)

def make_threat_model_prompt(summaries):
    claude_max_length = 128_000/4

    #deal with prompts that are too large by randomly sampling the summaries, since we can't deal with everything
    serialized_summary = None
    prompt = ""
    summaries = [f"Path: {path}, summary: {summary}" for path, summary in summaries]
    sample_size = len(summaries)

    while not serialized_summary or len(prompt) > claude_max_length:
        serialized_summary = ". ".join(random.sample(summaries, sample_size))
        prompt = (
            f"<s>You are an expert security architect. Create a threat model diagram based on the provided documentation.\n\n"
            f"Requirements:\n"
            f"1. Use mermaid.js flowchart TD syntax\n"
            f"2. Node types:\n"
            f"   - ((name)) for external entities/users\n"
            f"   - [name] for internal processes\n"
            f"   - [(name)] for data stores\n"
            f"   - {{{{name}}}} for security controls\n"
            f"   - >name] for outputs\n\n"
            f"3. Node Labels MUST:\n"
            f"   - Extract ACTUAL application name from the documentation (e.g., if docs mention 'MyApp', use 'MyApp')\n"
            f"   - Extract ACTUAL service names from the documentation (e.g., if docs mention 'auth-service', use 'auth-service')\n"
            f"   - Extract ACTUAL database names from the documentation (e.g., if docs mention 'users-db', use 'users-db')\n"
            f"   - Extract ACTUAL API service names from the documentation (e.g., if docs mention 'orders-api', use 'orders-api')\n"
            f"   - NEVER use generic names like 'example.com' or 'Web Browser'\n"
            f"   - NEVER make up names - use ONLY names found in the documentation\n\n"
            f"4. Data Flow Labels MUST:\n"
            f"   - Use ONLY alphanumeric characters, spaces, and underscores in labels\n"
            f"   - NO special characters like /, (, ), [, ], {{, }}, etc.\n"
            f"   - Be SPECIFIC about the data being transmitted (e.g., 'user_login_credentials' instead of 'auth_request')\n"
            f"   - Include the type of data (e.g., 'user_profile_data' instead of 'http_request')\n"
            f"   - For API endpoints, use format: 'create_user_profile_data' instead of 'api_tickets_create'\n"
            f"   - For state changes, use format: 'raw_user_data_to_validated' instead of 'raw_to_validated'\n"
            f"   - For data fields, use format: 'user_id_and_permissions' instead of 'user_id_roles'\n"
            f"   - Use actual field names and types from the documentation\n\n"
            f"5. Trust Boundaries:\n"
            f"   - Use subgraphs with descriptive names based on actual system zones\n"
            f"   - Label cross-boundary data flows with specific protocols/methods\n"
            f"   - Use format: 'encrypted_user_credentials' instead of 'http_request'\n\n"
            f"Example structure (using specific data types):\n"
            f"```mermaid\n"
            f"flowchart TD\n"
            f"    %% Styles\n"
            f"    classDef user fill:#fdd,stroke:#333,stroke-width:2px\n"
            f"    classDef process fill:#ddf,stroke:#333,stroke-width:2px\n"
            f"    classDef storage fill:#dfd,stroke:#333,stroke-width:2px\n"
            f"    classDef control fill:#fff,stroke:#f66,stroke-width:3px\n"
            f"    classDef external fill:#fdb,stroke:#333,stroke-width:2px\n"
            f"    \n"
            f"    %% Trust Boundaries\n"
            f"    subgraph ClientZone[MyApp]\n"
            f"        User((Customer))\n"
            f"        Frontend[MyApp Frontend]\n"
            f"    end\n"
            f"    \n"
            f"    subgraph APIZone[MyApp API]\n"
            f"        Auth{{{{auth-service}}}}\n"
            f"        API[orders-service]\n"
            f"        DB[(orders-db)]\n"
            f"    end\n"
            f"    \n"
            f"    %% Data Flows with Specific Types\n"
            f"    User -->|user_login_credentials| Frontend\n"
            f"    Frontend -->|encrypted_user_credentials| Auth\n"
            f"    Auth -->|validated_user_session| API\n"
            f"    API -->|order_transaction_data| DB\n"
            f"    DB -->|order_details_data| API\n"
            f"    API -->|order_confirmation_data| Frontend\n"
            f"    \n"
            f"    %% Apply styles\n"
            f"    class User user\n"
            f"    class Auth control\n"
            f"    class API process\n"
            f"    class DB storage\n"
            f"    class Frontend process\n"
            f"```\n\n"
            f"IMPORTANT:\n"
            f"1. Extract ACTUAL application and service names from the documentation - NEVER use generic examples\n"
            f"2. Convert all API endpoints to safe format but include data type (e.g., 'create_user_profile_data')\n"
            f"3. Show REAL data transformations between components\n"
            f"4. Label boundaries based on ACTUAL system architecture\n"
            f"5. Include only components and flows from documentation\n"
            f"6. Make data flow labels as specific as possible about the actual data being transmitted\n"
            f"7. Return ONLY the mermaid.js diagram\n"
            f"8. Use ONLY safe characters in labels (alphanumeric, spaces, underscores)\n\n"
            f"Documentation to analyze:\n{serialized_summary}\n"
            f"[/INST]"
        )
        sample_size -= 1
    sample_size += 1

    if sample_size != len(summaries):
        tqdm.write(f"Warning: Codebase is large, reducing modelling accuracy to {round(100/len(summaries)*sample_size)}%...") #we should calculate how much accuracy we're losing
    return prompt

def refine_threat_model_prompt(summaries, graph):
    claude_max_length = 128_000/4

    #deal with prompts that are too large by randomly sampling the summaries, since we can't deal with everything
    serialized_summary = None
    prompt = ""
    summaries = [f"Path: {path}, summary: {summary}" for path, summary in summaries]
    sample_size = len(summaries)

    while not serialized_summary or len(prompt) > claude_max_length:
        serialized_summary = ". ".join(random.sample(summaries, sample_size))
        prompt = (
            f"<s><instructions>You are an expert security architect. Refine the given threat model based on the documentation.\n\n"
            f"Requirements:\n"
            f"1. Use mermaid.js flowchart TD syntax\n"
            f"2. Node types:\n"
            f"   - ((name)) for external entities/users\n"
            f"   - [name] for internal processes\n"
            f"   - [(name)] for data stores\n"
            f"   - {{{{name}}}} for security controls\n"
            f"   - >name] for outputs\n\n"
            f"3. Node Labels MUST:\n"
            f"   - Extract ACTUAL application name from the documentation (e.g., if docs mention 'MyApp', use 'MyApp')\n"
            f"   - Extract ACTUAL service names from the documentation (e.g., if docs mention 'auth-service', use 'auth-service')\n"
            f"   - Extract ACTUAL database names from the documentation (e.g., if docs mention 'users-db', use 'users-db')\n"
            f"   - Extract ACTUAL API service names from the documentation (e.g., if docs mention 'orders-api', use 'orders-api')\n"
            f"   - NEVER use generic names like 'example.com' or 'Web Browser'\n"
            f"   - NEVER make up names - use ONLY names found in the documentation\n\n"
            f"4. Data Flow Labels MUST:\n"
            f"   - Use ONLY alphanumeric characters, spaces, and underscores in labels\n"
            f"   - NO special characters like /, (, ), [, ], {{, }}, etc.\n"
            f"   - Be SPECIFIC about the data being transmitted (e.g., 'user_login_credentials' instead of 'auth_request')\n"
            f"   - Include the type of data (e.g., 'user_profile_data' instead of 'http_request')\n"
            f"   - For API endpoints, use format: 'create_user_profile_data' instead of 'api_tickets_create'\n"
            f"   - For state changes, use format: 'raw_user_data_to_validated' instead of 'raw_to_validated'\n"
            f"   - For data fields, use format: 'user_id_and_permissions' instead of 'user_id_roles'\n"
            f"   - Use actual field names and types from the documentation\n\n"
            f"5. Trust Boundaries:\n"
            f"   - Use subgraphs with descriptive names based on actual system zones\n"
            f"   - Label cross-boundary data flows with specific protocols/methods\n"
            f"   - Use format: 'encrypted_user_credentials' instead of 'http_request'\n\n"
            f"Example structure (using specific data types):\n"
            f"```mermaid\n"
            f"flowchart TD\n"
            f"    %% Styles\n"
            f"    classDef user fill:#fdd,stroke:#333,stroke-width:2px\n"
            f"    classDef process fill:#ddf,stroke:#333,stroke-width:2px\n"
            f"    classDef storage fill:#dfd,stroke:#333,stroke-width:2px\n"
            f"    classDef control fill:#fff,stroke:#f66,stroke-width:3px\n"
            f"    classDef external fill:#fdb,stroke:#333,stroke-width:2px\n"
            f"    \n"
            f"    %% Trust Boundaries\n"
            f"    subgraph ClientZone[MyApp]\n"
            f"        User((Customer))\n"
            f"        Frontend[MyApp Frontend]\n"
            f"    end\n"
            f"    \n"
            f"    subgraph APIZone[MyApp API]\n"
            f"        Auth{{{{auth-service}}}}\n"
            f"        API[orders-service]\n"
            f"        DB[(orders-db)]\n"
            f"    end\n"
            f"    \n"
            f"    %% Data Flows with Specific Types\n"
            f"    User -->|user_login_credentials| Frontend\n"
            f"    Frontend -->|encrypted_user_credentials| Auth\n"
            f"    Auth -->|validated_user_session| API\n"
            f"    API -->|order_transaction_data| DB\n"
            f"    DB -->|order_details_data| API\n"
            f"    API -->|order_confirmation_data| Frontend\n"
            f"    \n"
            f"    %% Apply styles\n"
            f"    class User user\n"
            f"    class Auth control\n"
            f"    class API process\n"
            f"    class DB storage\n"
            f"    class Frontend process\n"
            f"```\n\n"
            f"IMPORTANT:\n"
            f"1. Extract ACTUAL application and service names from the documentation - NEVER use generic examples\n"
            f"2. Convert all API endpoints to safe format but include data type (e.g., 'create_user_profile_data')\n"
            f"3. Show REAL data transformations between components\n"
            f"4. Label boundaries based on ACTUAL system architecture\n"
            f"5. Include only components and flows from documentation\n"
            f"6. Make data flow labels as specific as possible about the actual data being transmitted\n"
            f"7. Return ONLY the mermaid.js diagram\n"
            f"8. Use ONLY safe characters in labels (alphanumeric, spaces, underscores)\n\n</instructions>"
            f"<documentation>\n{serialized_summary}</documentation>\n"
            f"<graph>\n{graph}</graph>\n"
            f"[/INST]"
        )
        sample_size -= 1
    sample_size += 1

    if sample_size != len(summaries):
        tqdm.write(f"Warning: Codebase is large, reducing modelling accuracy to {round(100/len(summaries)*sample_size)}%...") #we should calculate how much accuracy we're losing
    return prompt

# Analyzes code documentation to identify potential business logic issues and vulnerabilities.
# Identifies issues like inconsistent error handling, missing edge cases,
# potential race conditions, security vulnerabilities, and business rule violations.
# Input: documentation (str) - documentation to analyze, lang (str) - programming language
# Output: str - numbered list of identified potential flaws with descriptions
def generate_threat_model_diagram(summaries):
    """Generate a security-focused threat model diagram using mermaid.js"""

    #we need to add something here so that it verifies the syntax of the mermaid diagram and retries if it comes out wrong
    try:
        prompt = make_threat_model_prompt(summaries)

        diagram = bedrock_generate(prompt, model_id='anthropic.claude-3-sonnet-20240229-v1:0')

        if "```mermaid" in diagram:
            diagram = diagram[diagram.find("```mermaid"):diagram.rfind("```")]
            diagram = diagram.replace("```mermaid", "").replace("```", "").strip()

        # Ensure the diagram has the required elements
        required_elements = ["flowchart TD", "classDef", "-->", "subgraph"]
        if not all(x in diagram for x in required_elements):
            raise ValueError("Invalid diagram structure")

        prompt = refine_threat_model_prompt(summaries, diagram)

        diagram = bedrock_generate(prompt, model_id='anthropic.claude-3-sonnet-20240229-v1:0')

        if "```mermaid" in diagram:
            diagram = diagram[diagram.find("```mermaid"):diagram.rfind("```")]
            diagram = diagram.replace("```mermaid", "").replace("```", "").strip()

        # Ensure the diagram has the required elements
        required_elements = ["flowchart TD", "classDef", "-->", "subgraph"]
        if not all(x in diagram for x in required_elements):
            raise ValueError("Invalid diagram structure")

        return diagram

    except Exception as e:
        tqdm.write(f"Error generating threat model diagram: {str(e)}")
        traceback.print_exc()

        return """flowchart TD
    %% Styles
    classDef user fill:#fdd,stroke:#333,stroke-width:2px
    classDef process fill:#ddf,stroke:#333,stroke-width:2px
    classDef storage fill:#dfd,stroke:#333,stroke-width:2px
    classDef control fill:#fff,stroke:#f66,stroke-width:3px
    classDef external fill:#fdb,stroke:#333,stroke-width:2px

    %% Trust Boundaries
    subgraph ClientZone[MyApp]
        User((Customer))
        Frontend[MyApp Frontend]
    end

    subgraph APIZone[MyApp API]
        Auth{{auth-service}}
        API[orders-service]
        DB[(orders-db)]
    end

    %% Data Flows with Specific Types
    User -->|user_login_credentials| Frontend
    Frontend -->|encrypted_user_credentials| Auth
    Auth -->|validated_user_session| API
    API -->|order_transaction_data| DB
    DB -->|order_details_data| API
    API -->|order_confirmation_data| Frontend

    %% Apply styles
    class User user
    class Auth control
    class API process
    class DB storage
    class Frontend process"""

def get_gitignore_spec(repo_path):
    """Load .gitignore patterns into a GitIgnoreSpec"""
    gitignore_path = os.path.join(repo_path, '.gitignore')
    if os.path.exists(gitignore_path):
        with open(gitignore_path, 'r') as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith('#')] + ['.git/']
            return GitIgnoreSpec.from_lines(lines)
    return None

def truncate_code(code: str, section_regex: str) -> str:
    max_tokens = 8192
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

def process_file(args):
    repo_path, repo_file_path, changed_files, cache_path, cache, new_cache, config = args
    file_path = os.path.join(repo_path, repo_file_path)
    ext = os.path.splitext(file_path)[-1].lower()
    lang = next((k for k, v in config.items() if ext in v['extensions']), None)

    try:
        with open(file_path, 'r') as f:
            original_code = f.read()

        section_regex = config[lang]['section_regex']
        truncated_code = truncate_code(original_code, section_regex)
    except Exception as e:
        tqdm.write(f"Error reading {file_path}: {str(e)}")
        traceback.print_exc()
        return (False, None, None, None, None)

    summary = ""
    doc = ""
    # Store individual file documentation in the files subdirectory
    docs_dir = os.path.join(repo_path, 'wraith.docs')
    files_dir = os.path.join(docs_dir, 'files')
    os.makedirs(files_dir, exist_ok=True)
    doc_path = os.path.join(files_dir, f"{os.path.basename(file_path)}.docs.md")

    if repo_file_path in changed_files:
        try:
            tqdm.write(f"{file_path} ({lang}) has changed, processing...")
            doc = generate_documentation(truncated_code, file_path)

            with open(doc_path, 'w') as f:
                f.write(f"# {lang.capitalize()} Code Documentation\n")
                f.write(doc)

            summary = generate_summary(doc, file_path)
        except Exception as e:
            tqdm.write(f"Error generating documentation for {file_path}: {str(e)}")
            traceback.print_exc()
            return (False, None, None, None, None)
    else:
        try:
            if os.path.exists(doc_path):
                with open(doc_path, 'r') as f:
                    doc = f.read()
                summary = cache['summaries'][repo_file_path]
        except Exception as e:
            tqdm.write(f"Error reading existing documentation for {file_path}: {str(e)}")
            traceback.print_exc()
            return (False, None, None, None, None)
    return (True, repo_file_path, file_path, summary, doc)

def process_repository(repo_path: str, config: Dict):
    """Process all code files in the repository while respecting .gitignore"""
    summaries = []
    doc_contents = []  # Store full documentation content
    spec = get_gitignore_spec(repo_path)

    # Create documentation directories
    docs_dir = os.path.join(repo_path, 'wraith.docs')
    files_dir = os.path.join(docs_dir, 'files')
    os.makedirs(docs_dir, exist_ok=True)
    os.makedirs(files_dir, exist_ok=True)

    # Filter out ignored files
    filtered_files = []
    for root, dirs, files in os.walk(repo_path, topdown=True):
        rel_dir = os.path.relpath(root, repo_path).replace('\\', '/')
        if spec:
            dir_ignored = spec.match_file(rel_dir) or spec.match_file(f"{rel_dir}/")
            if dir_ignored:
                dirs[:] = []
                continue

        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, repo_path).replace('\\', '/')

            if spec and spec.match_file(rel_path):
                continue

            if should_ignore_file(rel_path):
                continue

            ext = os.path.splitext(file_path)[-1].lower()
            lang = next((k for k, v in config.items() if ext in v['extensions']), None)
            if lang:
                filtered_files.append(os.path.relpath(os.path.abspath(os.path.join(root, file)), os.path.abspath(repo_path)))

    cache_path = os.path.join(docs_dir, '.wraith.cache.json')
    changed_files, new_cache = compute_cache(repo_path, filtered_files, cache_path)

    try:
        with open(cache_path, 'r') as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cache = {'hashes': {}, 'summaries': {}}

    if 'hashes' not in cache:
        cache['hashes'] = {}
    if 'summaries' not in cache:
        cache['summaries'] = {}

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(process_file, (repo_path, repo_file_path, changed_files, cache_path, cache, new_cache, config)) for repo_file_path in filtered_files]
        with tqdm(total=len(futures), miniters=1, mininterval=0.1, colour='green', position=0, desc="Generating documentation") as pbar:
            for future in as_completed(futures):
                success, repo_file_path, file_path, summary, doc = future.result()
                pbar.update(1)
                if not success:
                    continue


                #only update hashes if we succeeded
                doc_contents.append((file_path, doc))
                cache['hashes'][repo_file_path] = new_cache['hashes'][repo_file_path]

                if summary:
                    summaries.append((file_path, summary))
                    cache['summaries'][repo_file_path] = summary

    for path in list(cache['hashes'].keys()):
        if path not in new_cache['hashes']:
            del cache['hashes'][path]
            if path in cache['summaries']:
                del cache['summaries'][path]

    with open(cache_path, 'w') as f:
        json.dump(cache, f, indent=4)

    try:
        summary_path = os.path.join(docs_dir, 'summary.docs.md')
        with open(summary_path, 'w') as f:
            f.write("# Repository Overview\n\n")
            for path, summary in summaries:
                rel_path = os.path.relpath(path, repo_path).replace('\\', '/')
                f.write(f"## {rel_path}\n\n{summary}\n\n")
    except Exception as e:
        tqdm.write(f"Error creating summary: {str(e)}")

    # Generate data flow diagram
    diagram_path = os.path.join(docs_dir, 'system-dataflow.md')
    try:
        tqdm.write(f"Documentation generated, generating threat model diagram...")
        # Generate the diagram using the comprehensive documentation
        diagram = generate_threat_model_diagram(summaries)

        # Write only the raw mermaid diagram to the file
        with open(diagram_path, 'w') as f:
            f.write(diagram)

    except Exception as e:
        tqdm.write(f"Error creating data flow diagram: {str(e)}")
        traceback.print_exc()

    return doc_contents

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Repository Code Processor')
    parser.add_argument('repo_path', type=str, nargs='?', default='', help='Path to the repository')
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
            tqdm.write(f"Error loading config file: {e}")
            return

    # Set up language processing configuration
    enable_langs = args.enable_languages.split(',') if args.enable_languages else config.get('enable_languages', [])
    disable_langs = args.disable_languages.split(',') if args.disable_languages else config.get('disable_languages', [])

    language_config = get_language_config(enable_langs, disable_langs)

    if args.repo_path:
        # Process the repository
        try:
            result = process_repository(
                args.repo_path,
                language_config
            )
        except Exception as e:
            tqdm.write(f"Processing failed: {e}")
            traceback.print_exc()
    else:
        # Boot the HTTP server if we're not trying to process a specific repo
        bottle.run(host='0.0.0.0', port=3000, debug=True, reloader=True)


if __name__ == '__main__':
    main()
