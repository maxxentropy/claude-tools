#!/usr/bin/env python3
"""
find_endpoints.py - Extract ASP.NET API endpoints from a codebase.

Usage:
    python find_endpoints.py /path/to/codebase
    python find_endpoints.py /path/to/codebase --output endpoints.json

Detects:
    - Controller classes ([ApiController], [Controller])
    - HTTP method attributes ([HttpGet], [HttpPost], etc.)
    - Route templates ([Route], [HttpGet("path")])
    - Action parameters and return types
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class EndpointParameter:
    """A parameter for an API endpoint."""
    name: str
    type: str
    source: str = "unknown"  # query, route, body, header, form


@dataclass
class Endpoint:
    """A single API endpoint."""
    http_method: str
    route: str
    action_name: str
    controller: str
    file_path: str
    line_number: int
    return_type: str = ""
    parameters: list = field(default_factory=list)
    attributes: list = field(default_factory=list)
    summary: str = ""


@dataclass
class ControllerInfo:
    """Information about an API controller."""
    name: str
    file_path: str
    relative_path: str
    base_route: str = ""
    endpoints: list = field(default_factory=list)
    is_api_controller: bool = False
    base_class: str = ""


@dataclass
class ApiSummary:
    """Summary of all APIs in the codebase."""
    root_path: str
    controllers: list = field(default_factory=list)
    total_endpoints: int = 0
    endpoints_by_method: dict = field(default_factory=dict)


# Regex patterns for detection
PATTERNS = {
    # Controller detection
    "api_controller_attr": re.compile(r"\[ApiController\]"),
    "controller_class": re.compile(
        r"(?:public\s+)?class\s+(\w+Controller)\s*(?:<[^>]+>)?\s*:\s*(\w+)"
    ),
    "controller_base_route": re.compile(
        r'\[Route\(\s*["\']([^"\']+)["\']\s*\)\]'
    ),
    
    # HTTP method attributes
    "http_get": re.compile(
        r'\[HttpGet(?:\(\s*["\']?([^"\')\]]*)["\']?\s*\))?\]'
    ),
    "http_post": re.compile(
        r'\[HttpPost(?:\(\s*["\']?([^"\')\]]*)["\']?\s*\))?\]'
    ),
    "http_put": re.compile(
        r'\[HttpPut(?:\(\s*["\']?([^"\')\]]*)["\']?\s*\))?\]'
    ),
    "http_delete": re.compile(
        r'\[HttpDelete(?:\(\s*["\']?([^"\')\]]*)["\']?\s*\))?\]'
    ),
    "http_patch": re.compile(
        r'\[HttpPatch(?:\(\s*["\']?([^"\')\]]*)["\']?\s*\))?\]'
    ),
    
    # Action method signature
    "action_method": re.compile(
        r"(?:public\s+)?(?:async\s+)?(?:virtual\s+)?"
        r"([\w<>,\s\[\]]+?)\s+"  # Return type
        r"(\w+)\s*"              # Method name
        r"\(([^)]*)\)"           # Parameters
    ),
    
    # Parameter attributes
    "from_body": re.compile(r"\[FromBody\]"),
    "from_query": re.compile(r"\[FromQuery[^\]]*\]"),
    "from_route": re.compile(r"\[FromRoute[^\]]*\]"),
    "from_header": re.compile(r"\[FromHeader[^\]]*\]"),
    "from_form": re.compile(r"\[FromForm[^\]]*\]"),
    
    # Documentation
    "xml_summary": re.compile(r"<summary>\s*(.*?)\s*</summary>", re.DOTALL),
    
    # Authorization
    "authorize_attr": re.compile(r"\[Authorize[^\]]*\]"),
    "allow_anonymous": re.compile(r"\[AllowAnonymous\]"),
}

HTTP_METHODS = ["http_get", "http_post", "http_put", "http_delete", "http_patch"]


def find_controller_files(root_path: Path) -> list[Path]:
    """Find all potential controller files."""
    controller_files = []
    
    for cs_file in root_path.rglob("*.cs"):
        # Skip obj and bin directories
        path_str = str(cs_file)
        if "/obj/" in path_str or "\\obj\\" in path_str:
            continue
        if "/bin/" in path_str or "\\bin\\" in path_str:
            continue
        
        # Check if filename suggests it's a controller
        if "Controller" in cs_file.name:
            controller_files.append(cs_file)
            continue
            
        # Or check file content for controller indicators
        try:
            content = cs_file.read_text(encoding="utf-8", errors="ignore")
            if "[ApiController]" in content or ": ControllerBase" in content:
                controller_files.append(cs_file)
        except Exception:
            pass
    
    return controller_files


def parse_parameters(param_string: str) -> list[EndpointParameter]:
    """Parse method parameters into structured data."""
    if not param_string.strip():
        return []
    
    parameters = []
    # Split by comma, but be careful of generic types
    depth = 0
    current = ""
    
    for char in param_string:
        if char == "<":
            depth += 1
        elif char == ">":
            depth -= 1
        elif char == "," and depth == 0:
            if current.strip():
                parameters.append(current.strip())
            current = ""
            continue
        current += char
    
    if current.strip():
        parameters.append(current.strip())
    
    result = []
    for param in parameters:
        # Extract parameter source
        source = "unknown"
        if PATTERNS["from_body"].search(param):
            source = "body"
        elif PATTERNS["from_query"].search(param):
            source = "query"
        elif PATTERNS["from_route"].search(param):
            source = "route"
        elif PATTERNS["from_header"].search(param):
            source = "header"
        elif PATTERNS["from_form"].search(param):
            source = "form"
        
        # Remove attributes
        param_clean = re.sub(r"\[[^\]]+\]\s*", "", param).strip()
        
        # Split into type and name
        parts = param_clean.rsplit(" ", 1)
        if len(parts) == 2:
            param_type, param_name = parts
            # Remove default value if present
            param_name = param_name.split("=")[0].strip()
            result.append(EndpointParameter(
                name=param_name,
                type=param_type.strip(),
                source=source
            ))
    
    return result


def extract_endpoints_from_controller(
    content: str,
    file_path: Path,
    root_path: Path
) -> Optional[ControllerInfo]:
    """Extract controller and endpoint information from a C# file."""
    
    # Check if this is a controller
    is_api = bool(PATTERNS["api_controller_attr"].search(content))
    controller_match = PATTERNS["controller_class"].search(content)
    
    if not controller_match:
        return None
    
    controller_name = controller_match.group(1)
    base_class = controller_match.group(2)
    
    # Not a web controller
    if base_class not in ["ControllerBase", "Controller", "ApiController"]:
        # Could still be inheriting from a custom base
        if not is_api and "[HttpGet]" not in content and "[HttpPost]" not in content:
            return None
    
    controller = ControllerInfo(
        name=controller_name,
        file_path=str(file_path),
        relative_path=str(file_path.relative_to(root_path)),
        is_api_controller=is_api,
        base_class=base_class
    )
    
    # Find base route
    route_match = PATTERNS["controller_base_route"].search(content)
    if route_match:
        controller.base_route = route_match.group(1)
    
    # Find all endpoints
    lines = content.split("\n")
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Look for HTTP method attributes
        for method_name in HTTP_METHODS:
            match = PATTERNS[method_name].search(line)
            if match:
                route_template = match.group(1) if match.lastindex else ""
                
                # Collect all attributes until we hit the method
                attributes = []
                method_line_idx = i
                
                # Look ahead for the actual method
                j = i
                while j < len(lines):
                    attr_line = lines[j].strip()
                    
                    # Collect attributes
                    if attr_line.startswith("["):
                        attributes.append(attr_line)
                    
                    # Check for method signature
                    action_match = PATTERNS["action_method"].search(lines[j])
                    if action_match and not lines[j].strip().startswith("["):
                        return_type = action_match.group(1).strip()
                        action_name = action_match.group(2)
                        params_str = action_match.group(3)
                        
                        # Build full route
                        full_route = controller.base_route
                        if route_template:
                            if full_route:
                                full_route = f"{full_route}/{route_template}"
                            else:
                                full_route = route_template
                        
                        # Replace [controller] placeholder
                        controller_short = controller_name.replace("Controller", "")
                        full_route = full_route.replace("[controller]", controller_short.lower())
                        full_route = full_route.replace("[action]", action_name.lower())
                        
                        # Check for authorization
                        if PATTERNS["authorize_attr"].search("\n".join(lines[i:j+1])):
                            attributes.append("[Authorize]")
                        if PATTERNS["allow_anonymous"].search("\n".join(lines[i:j+1])):
                            attributes.append("[AllowAnonymous]")
                        
                        endpoint = Endpoint(
                            http_method=method_name.replace("http_", "").upper(),
                            route=full_route or f"/{controller_short.lower()}/{action_name.lower()}",
                            action_name=action_name,
                            controller=controller_name,
                            file_path=str(file_path.relative_to(root_path)),
                            line_number=j + 1,
                            return_type=return_type,
                            parameters=[asdict(p) for p in parse_parameters(params_str)],
                            attributes=attributes
                        )
                        
                        controller.endpoints.append(endpoint)
                        i = j
                        break
                    
                    j += 1
                    if j > i + 20:  # Don't look too far ahead
                        break
                
                break
        
        i += 1
    
    return controller if controller.endpoints else None


def scan_api_endpoints(root_path: str) -> ApiSummary:
    """Scan a codebase for all API endpoints."""
    root = Path(root_path).resolve()
    
    if not root.exists():
        raise ValueError(f"Path does not exist: {root_path}")
    
    summary = ApiSummary(root_path=str(root))
    
    # Find all potential controller files
    controller_files = find_controller_files(root)
    
    for cs_file in controller_files:
        try:
            content = cs_file.read_text(encoding="utf-8", errors="ignore")
            controller = extract_endpoints_from_controller(content, cs_file, root)
            
            if controller:
                summary.controllers.append(controller)
                summary.total_endpoints += len(controller.endpoints)
                
                for endpoint in controller.endpoints:
                    method = endpoint.http_method
                    if method not in summary.endpoints_by_method:
                        summary.endpoints_by_method[method] = 0
                    summary.endpoints_by_method[method] += 1
                    
        except Exception as e:
            print(f"Warning: Error processing {cs_file}: {e}", file=sys.stderr)
    
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Extract ASP.NET API endpoints from a codebase."
    )
    parser.add_argument(
        "path",
        help="Path to the codebase root directory"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: stdout)",
        default=None
    )
    parser.add_argument(
        "--pretty", "-p",
        help="Pretty print JSON output",
        action="store_true",
        default=True
    )
    
    args = parser.parse_args()
    
    try:
        summary = scan_api_endpoints(args.path)
        
        # Convert to dict for JSON serialization
        result = asdict(summary)
        
        # Output
        indent = 2 if args.pretty else None
        json_output = json.dumps(result, indent=indent)
        
        if args.output:
            Path(args.output).write_text(json_output)
            print(f"Endpoints written to {args.output}", file=sys.stderr)
        else:
            print(json_output)
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
