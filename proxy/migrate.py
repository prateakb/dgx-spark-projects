import os
import re

def migrate():
    # Configuration
    source_file = "server.py" # Change this if your file is named differently
    output_dir = "proxy_project"
    
    if not os.path.exists(output_dir):
        os.makedirs(f"{output_dir}/app")
        open(f"{output_dir}/app/__init__.py", "a").close()

    with open(source_file, "r") as f:
        content = f.read()

    # Define the file chunks using regex or manual slicing
    # Note: In a real scenario, we'd use AST, but regex is faster for a "one-off" shift
    
    ### 1. Create app/utils.py
    utils_content = """import logging
import json
from typing import Any

class MessageFilter(logging.Filter):
    def filter(self, record):
        blocked_phrases = ["LiteLLM completion()", "HTTP Request:", "selected model name for cost calculation", "utils.py", "cost_calculator"]
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            for phrase in blocked_phrases:
                if phrase in record.msg: return False
        return True

class ColorizedFormatter(logging.Formatter):
    BLUE, GREEN, YELLOW, RED, RESET, BOLD = "\\033[94m", "\\033[92m", "\\033[93m", "\\033[91m", "\\033[0m", "\\033[1m"
    def format(self, record):
        if record.levelno == logging.DEBUG and "MODEL MAPPING" in record.msg:
            return f"{self.BOLD}{self.GREEN}{record.msg}{self.RESET}"
        return super().format(record)

def clean_gemini_schema(schema: Any) -> Any:
    if isinstance(schema, dict):
        schema.pop("additionalProperties", None)
        schema.pop("default", None)
        if schema.get("type") == "string" and "format" in schema:
            if schema["format"] not in {"enum", "date-time"}: schema.pop("format")
        for key, value in list(schema.items()): schema[key] = clean_gemini_schema(value)
    elif isinstance(schema, list):
        return [clean_gemini_schema(item) for item in schema]
    return schema

class Colors:
    CYAN, BLUE, GREEN, YELLOW, RED, MAGENTA, RESET, BOLD = "\\033[96m", "\\033[94m", "\\033[92m", "\\033[93m", "\\033[91m", "\\033[95m", "\\033[0m", "\\033[1m"
"""
    with open(f"{output_dir}/app/utils.py", "w") as f:
        f.write(utils_content)

    ### 2. Create app/models.py
    # This extracts all Pydantic classes
    models = re.findall(r"class .*?\(BaseModel\):.*?((?=\nclass)|(?=\ndef)|$)", content, re.DOTALL)
    with open(f"{output_dir}/app/models.py", "w") as f:
        f.write("from pydantic import BaseModel, Field, field_validator, model_validator\n")
        f.write("from typing import List, Dict, Any, Optional, Union, Literal\n")
        f.write("import logging\n\nlogger = logging.getLogger(__name__)\n\n")
        # Grab the constants needed for validation
        f.write("# Copy your BIG_MODEL, SMALL_MODEL, etc variables here from .env or config\n")
        for model_code in re.findall(r"class.*?\(BaseModel\):.*?(?=\nclass|\n#|\ndef|$)", content, re.DOTALL):
            f.write(model_code + "\n")

    ### 3. Create app/converter.py
    # This will hold the logic functions
    logic_funcs = ["coerce_tool_arguments", "convert_anthropic_to_litellm", "convert_litellm_to_anthropic", "parse_tool_result_content"]
    with open(f"{output_dir}/app/converter.py", "w") as f:
        f.write("import json, uuid, logging, litellm, os\nfrom typing import Any, Dict, List, Union\n")
        f.write("from app.models import *\nfrom app.utils import clean_gemini_schema\n\nlogger = logging.getLogger(__name__)\n\n")
        for func in logic_funcs:
            pattern = rf"def {func}\(.*?:\n(.*?)(?=\ndef|\n@|\nif __name__|$)"
            match = re.search(rf"def {func}.*?:\n.*?(?=\ndef|# ---|$)", content, re.DOTALL)
            if match:
                f.write(match.group(0) + "\n\n")

    print(f"✅ Successfully refactored into {output_dir}/")

if __name__ == "__main__":
    migrate()