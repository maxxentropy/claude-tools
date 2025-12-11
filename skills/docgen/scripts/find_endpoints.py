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
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class EndpointParameter:
    name: str
    type: str
    source: str = "unknown"


@dataclass
class Endpoint:
    http_method: str
    route: str
    action_name: str
    controller: str
    file_path: str
    line_number: int
    return_type: str = ""
    parameters: list = field(default_factory=list)
    attributes: list = field(default_factory=list)


@dataclass
class ControllerInfo:
    name: str
    file_path: str
    relative_path: str
    base_route: str = ""
    endpoints: list = field(default_factory=list)
    is_api_controller: bool = False
    base_class: str = ""


@dataclass
class ApiSummary:
    root_path: str
    controllers: list = field(default_factory=list)
    total_endpoints: int = 0
    endpoints_by_method: dict = field(default_factory=dict)


PATTERNS = {
    "api_controller_attr": re.compile(r"\[ApiController\]"),
    "controller_class": re.compile(r"(?:public\s+)?class\s+(\w+Controller)\s*(?:<[^>]+>)?\s*:\s*(\w+)"),
    "controller_base_route": re.compile(r'\[Route\(\s*["\']([^"\']+)["\']\s*\)\]'),
    "http_get": re.compile(r'\[HttpGet(?:\(\s*["\']?([^"\')\]]*)["\']?\s*\))?\]'),
    "http_post": re.compile(r'\[HttpPost(?:\(\s*["\']?([^"\')\]]*)["\']?\s*\))?\]'),
    "http_put": re.compile(r'\[HttpPut(?:\(\s*["\']?([^"\')\]]*)["\']?\s*\))?\]'),
    "http_delete": re.compile(r'\[HttpDelete(?:\(\s*["\']?([^"\')\]]*)["\']?\s*\))?\]'),
    "http_patch": re.compile(r'\[HttpPatch(?:\(\s*["\']?([^"\')\]]*)["\']?\s*\))?\]'),
    "action_method": re.compile(r"(?:public\s+)?(?:async\s+)?(?:virtual\s+)?([\w<>,\s\[\]]+?)\s+(\w+)\s*\(([^)]*)\)"),
    "from_body": re.compile(r"\[FromBody\]"),
    "from_query": re.compile(r"\[FromQuery[^\]]*\]"),
    "from_route": re.compile(r"\[FromRoute[^\]]*\]"),
    "authorize_attr": re.compile(r"\[Authorize[^\]]*\]"),
    "allow_anonymous": re.compile(r"\[AllowAnonymous\]"),
}

HTTP_METHODS = ["http_get", "http_post", "http_put", "http_delete", "http_patch"]


def find_controller_files(root_path: Path) -> list[Path]:
    controller_files = []
    for cs_file in root_path.rglob("*.cs"):
        path_str = str(cs_file)
        if "/obj/" in path_str or "\\obj\\" in path_str or "/bin/" in path_str or "\\bin\\" in path_str:
            continue
        if "Controller" in cs_file.name:
            controller_files.append(cs_file)
            continue
        try:
            content = cs_file.read_text(encoding="utf-8", errors="ignore")
            if "[ApiController]" in content or ": ControllerBase" in content:
                controller_files.append(cs_file)
        except Exception:
            pass
    return controller_files


def parse_parameters(param_string: str) -> list[EndpointParameter]:
    if not param_string.strip():
        return []
    
    parameters = []
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
        source = "unknown"
        if PATTERNS["from_body"].search(param):
            source = "body"
        elif PATTERNS["from_query"].search(param):
            source = "query"
        elif PATTERNS["from_route"].search(param):
            source = "route"
        
        param_clean = re.sub(r"\[[^\]]+\]\s*", "", param).strip()
        parts = param_clean.rsplit(" ", 1)
        if len(parts) == 2:
            param_type, param_name = parts
            param_name = param_name.split("=")[0].strip()
            result.append(EndpointParameter(name=param_name, type=param_type.strip(), source=source))
    
    return result


def extract_endpoints_from_controller(content: str, file_path: Path, root_path: Path) -> Optional[ControllerInfo]:
    is_api = bool(PATTERNS["api_controller_attr"].search(content))
    controller_match = PATTERNS["controller_class"].search(content)
    
    if not controller_match:
        return None
    
    controller_name = controller_match.group(1)
    base_class = controller_match.group(2)
    
    if base_class not in ["ControllerBase", "Controller", "ApiController"]:
        if not is_api and "[HttpGet]" not in content and "[HttpPost]" not in content:
            return None
    
    controller = ControllerInfo(
        name=controller_name,
        file_path=str(file_path),
        relative_path=str(file_path.relative_to(root_path)),
        is_api_controller=is_api,
        base_class=base_class
    )
    
    route_match = PATTERNS["controller_base_route"].search(content)
    if route_match:
        controller.base_route = route_match.group(1)
    
    lines = content.split("\n")
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        for method_name in HTTP_METHODS:
            match = PATTERNS[method_name].search(line)
            if match:
                route_template = match.group(1) if match.lastindex else ""
                attributes = []
                
                j = i
                while j < len(lines):
                    attr_line = lines[j].strip()
                    if attr_line.startswith("["):
                        attributes.append(attr_line)
                    
                    action_match = PATTERNS["action_method"].search(lines[j])
                    if action_match and not lines[j].strip().startswith("["):
                        return_type = action_match.group(1).strip()
                        action_name = action_match.group(2)
                        params_str = action_match.group(3)
                        
                        full_route = controller.base_route
                        if route_template:
                            full_route = f"{full_route}/{route_template}" if full_route else route_template
                        
                        controller_short = controller_name.replace("Controller", "")
                        full_route = full_route.replace("[controller]", controller_short.lower())
                        full_route = full_route.replace("[action]", action_name.lower())
                        
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
                    if j > i + 20:
                        break
                break
        i += 1
    
    return controller if controller.endpoints else None


def scan_api_endpoints(root_path: str) -> ApiSummary:
    root = Path(root_path).resolve()
    if not root.exists():
        raise ValueError(f"Path does not exist: {root_path}")
    
    summary = ApiSummary(root_path=str(root))
    
    for cs_file in find_controller_files(root):
        try:
            content = cs_file.read_text(encoding="utf-8", errors="ignore")
            controller = extract_endpoints_from_controller(content, cs_file, root)
            
            if controller:
                summary.controllers.append(controller)
                summary.total_endpoints += len(controller.endpoints)
                
                for endpoint in controller.endpoints:
                    method = endpoint.http_method
                    summary.endpoints_by_method[method] = summary.endpoints_by_method.get(method, 0) + 1
        except Exception as e:
            print(f"Warning: Error processing {cs_file}: {e}", file=sys.stderr)
    
    return summary


def main():
    parser = argparse.ArgumentParser(description="Extract ASP.NET API endpoints from a codebase.")
    parser.add_argument("path", help="Path to the codebase root directory")
    parser.add_argument("--output", "-o", help="Output file path (default: stdout)", default=None)
    parser.add_argument("--pretty", "-p", help="Pretty print JSON output", action="store_true", default=True)
    
    args = parser.parse_args()
    
    try:
        summary = scan_api_endpoints(args.path)
        result = asdict(summary)
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
