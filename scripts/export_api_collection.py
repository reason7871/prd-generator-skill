#!/usr/bin/env python3
"""
Generate API collection exports for Postman and Insomnia.
Auto-detects API endpoints from code and generates importable collections.
"""

import json
import re
import argparse
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from urllib.parse import urljoin


@dataclass
class APIEndpoint:
    """Represents an API endpoint."""
    method: str
    path: str
    name: str = ""
    description: str = ""
    handler: str = ""
    file: str = ""
    line: int = 0
    parameters: List[Dict] = field(default_factory=list)
    request_body: Optional[Dict] = None
    response_schema: Optional[Dict] = None
    headers: Dict[str, str] = field(default_factory=dict)
    auth_required: bool = False


class APICollectionGenerator:
    """Generate API collections from code analysis."""

    def __init__(self, base_url: str = "http://localhost:3000"):
        self.base_url = base_url
        self.endpoints: List[APIEndpoint] = []

    def analyze_file(self, file_path: str, content: str):
        """Analyze a file and extract API endpoints."""
        ext = Path(file_path).suffix.lower()

        if ext in ('.ts', '.tsx', '.js', '.jsx'):
            self._extract_js_endpoints(file_path, content)
        elif ext == '.py':
            self._extract_python_endpoints(file_path, content)
        elif ext == '.go':
            self._extract_go_endpoints(file_path, content)

    def _extract_js_endpoints(self, file_path: str, content: str):
        """Extract API endpoints from JavaScript/TypeScript files."""
        # Next.js App Router: route.ts files
        if 'route.ts' in file_path or 'route.js' in file_path:
            self._extract_nextjs_route(file_path, content)
            return

        # Express patterns
        patterns = [
            (r'app\.(get|post|put|delete|patch)\s*\(\s*[\'"]([^\'"]+)[\'"]', 'express'),
            (r'router\.(get|post|put|delete|patch)\s*\(\s*[\'"]([^\'"]+)[\'"]', 'express-router'),
            (r'(GET|POST|PUT|DELETE|PATCH)\s*\(\s*[\'"]([^\'"]+)[\'"]', 'fastify'),
            (r'@(\w+)\s*\(\s*[\'"]([^\'"]+)[\'"]', 'decorator'),
        ]

        for pattern, framework in patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                method = match.group(1).upper()
                path = match.group(2)

                # Extract handler name
                handler = self._extract_handler_name(content, match.end())

                endpoint = APIEndpoint(
                    method=method,
                    path=path,
                    name=f"{method} {path}",
                    handler=handler,
                    file=file_path,
                    line=content[:match.start()].count('\n') + 1
                )

                # Check for auth
                endpoint.auth_required = self._check_auth(content, match.start())

                self.endpoints.append(endpoint)

    def _extract_nextjs_route(self, file_path: str, content: str):
        """Extract API endpoints from Next.js App Router route.ts files."""
        # Extract route path from file path
        route_path = file_path
        if '/api/' in route_path:
            route_path = '/' + route_path.split('/api/')[-1].replace('/route.ts', '').replace('/route.js', '')
        elif '/app/' in route_path:
            route_path = '/' + route_path.split('/app/')[-1].replace('/route.ts', '').replace('/route.js', '')

        # Detect exported HTTP methods
        methods = []
        for method in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
            if re.search(rf'export\s+async\s+function\s+{method}\s*\(', content):
                methods.append(method)

        for method in methods:
            endpoint = APIEndpoint(
                method=method,
                path=route_path,
                name=f"{method} {route_path}",
                file=file_path,
                line=1
            )

            # Extract parameters from path
            params = re.findall(r'\[(\w+)\]', route_path)
            for param in params:
                endpoint.parameters.append({
                    'name': param,
                    'in': 'path',
                    'required': True,
                    'schema': {'type': 'string'}
                })

            # Check for query parameters in code
            query_params = re.findall(r'searchParams\.get\([\'"](\w+)[\'"]\)', content)
            for param in query_params:
                endpoint.parameters.append({
                    'name': param,
                    'in': 'query',
                    'required': False,
                    'schema': {'type': 'string'}
                })

            # Check for request body
            if 'request.json()' in content or 'req.body' in content:
                endpoint.request_body = {
                    'mode': 'raw',
                    'raw': '{\n  "key": "value"\n}',
                    'options': {'raw': {'language': 'json'}}
                }

            self.endpoints.append(endpoint)

    def _extract_python_endpoints(self, file_path: str, content: str):
        """Extract API endpoints from Python files (FastAPI, Flask, Django)."""
        # FastAPI decorators
        fastapi_pattern = r'@(app|router)\.(get|post|put|delete|patch)\s*\(\s*[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(fastapi_pattern, content, re.IGNORECASE):
            method = match.group(2).upper()
            path = match.group(3)

            endpoint = APIEndpoint(
                method=method,
                path=path,
                name=f"{method} {path}",
                file=file_path,
                line=content[:match.start()].count('\n') + 1
            )

            # Extract function parameters
            func_match = re.search(r'def\s+(\w+)\s*\(([^)]+)\)', content[match.end():match.end()+500])
            if func_match:
                endpoint.handler = func_match.group(1)

            self.endpoints.append(endpoint)

        # Flask routes
        flask_pattern = r'@app\.route\s*\(\s*[\'"]([^\'"]+)[\'"](?:,\s*methods\s*=\s*\[([^\]]+)\])?'
        for match in re.finditer(flask_pattern, content):
            path = match.group(1)
            methods_str = match.group(2) or '"GET"'

            methods = re.findall(r'[\'"](\w+)[\'"]', methods_str)
            for method in methods:
                endpoint = APIEndpoint(
                    method=method.upper(),
                    path=path,
                    name=f"{method.upper()} {path}",
                    file=file_path,
                    line=content[:match.start()].count('\n') + 1
                )
                self.endpoints.append(endpoint)

    def _extract_go_endpoints(self, file_path: str, content: str):
        """Extract API endpoints from Go files."""
        patterns = [
            r'(r\.)?HandleFunc\s*\(\s*[\'"]([^\'"]+)[\'"]',
            r'\.(GET|POST|PUT|DELETE|PATCH)\s*\(\s*[\'"]([^\'"]+)[\'"]',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, content):
                groups = match.groups()
                path = groups[-1]
                method = groups[-2] if len(groups) > 1 else 'GET'

                endpoint = APIEndpoint(
                    method=method.upper(),
                    path=path,
                    name=f"{method.upper()} {path}",
                    file=file_path,
                    line=content[:match.start()].count('\n') + 1
                )
                self.endpoints.append(endpoint)

    def _extract_handler_name(self, content: str, position: int) -> str:
        """Extract the handler function name near a position."""
        nearby = content[position:position + 300]
        match = re.search(r'(?:async\s+)?(?:function\s+)?(\w+)\s*(?:\(|=)', nearby)
        return match.group(1) if match else 'anonymous'

    def _check_auth(self, content: str, position: int) -> bool:
        """Check if authentication is required near an endpoint."""
        context = content[max(0, position - 500):position + 500]
        auth_indicators = ['auth', 'authenticate', 'token', 'session', 'jwt', 'bearer']
        return any(indicator in context.lower() for indicator in auth_indicators)

    def analyze_project(self, project_path: str):
        """Analyze an entire project for API endpoints."""
        project = Path(project_path)
        skip_dirs = {'node_modules', 'venv', '__pycache__', '.git', 'dist', 'build', '.next', 'coverage'}

        for root, dirs, files in os.walk(project):
            dirs[:] = [d for d in dirs if d not in skip_dirs]

            for file in files:
                ext = Path(file).suffix.lower()
                if ext in ('.ts', '.tsx', '.js', '.jsx', '.py', '.go'):
                    file_path = Path(root) / file
                    try:
                        content = file_path.read_text(encoding='utf-8', errors='ignore')
                        rel_path = str(file_path.relative_to(project))
                        self.analyze_file(rel_path, content)
                    except Exception as e:
                        print(f"Warning: Could not analyze {file_path}: {e}")

    def to_postman(self) -> Dict:
        """Generate Postman collection."""
        collection = {
            "info": {
                "name": "API Collection",
                "description": "Auto-generated from code analysis",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
            },
            "auth": {
                "type": "bearer",
                "bearer": [{"key": "token", "value": "{{api_token}}"}]
            },
            "item": []
        }

        # Group endpoints by path prefix
        groups = {}
        for endpoint in self.endpoints:
            prefix = '/' + endpoint.path.strip('/').split('/')[0] if '/' in endpoint.path.strip('/') else 'root'
            if prefix not in groups:
                groups[prefix] = []
            groups[prefix].append(endpoint)

        for group_name, endpoints in groups.items():
            folder = {
                "name": group_name.replace('/', '').title() or "Root",
                "item": []
            }

            for ep in endpoints:
                item = {
                    "name": ep.name or f"{ep.method} {ep.path}",
                    "request": {
                        "method": ep.method,
                        "header": [
                            {"key": "Content-Type", "value": "application/json"}
                        ],
                        "url": {
                            "raw": f"{{{{base_url}}}}{ep.path}",
                            "host": ["{{base_url}}"],
                            "path": ep.path.strip('/').split('/')
                        },
                        "description": f"Handler: {ep.handler}\nFile: {ep.file}:{ep.line}"
                    }
                }

                # Add query parameters
                query_params = [p for p in ep.parameters if p.get('in') == 'query']
                if query_params:
                    item["request"]["url"]["query"] = [
                        {"key": p["name"], "value": "", "disabled": not p.get("required", False)}
                        for p in query_params
                    ]

                # Add request body
                if ep.request_body:
                    item["request"]["body"] = ep.request_body

                # Add auth info
                if ep.auth_required:
                    item["request"]["auth"] = {"type": "bearer"}

                folder["item"].append(item)

            collection["item"].append(folder)

        # Add variables
        collection["variable"] = [
            {"key": "base_url", "value": self.base_url},
            {"key": "api_token", "value": ""}
        ]

        return collection

    def to_insomnia(self) -> Dict:
        """Generate Insomnia collection."""
        collection = {
            "_type": "export",
            "__export_format": 4,
            "__export_date": "2024-01-01T00:00:00.000Z",
            "__export_source": "prd-generator",
            "resources": []
        }

        # Add workspace
        workspace_id = "wrk_1"
        collection["resources"].append({
            "_id": workspace_id,
            "_type": "workspace",
            "name": "API Collection",
            "description": "Auto-generated from code analysis"
        })

        # Add environment
        env_id = "env_1"
        collection["resources"].append({
            "_id": env_id,
            "_type": "environment",
            "parentId": workspace_id,
            "name": "Base Environment",
            "data": {
                "base_url": self.base_url,
                "api_token": ""
            }
        })

        # Add endpoints as requests
        for i, ep in enumerate(self.endpoints):
            request_id = f"req_{i}"

            request = {
                "_id": request_id,
                "_type": "request",
                "parentId": workspace_id,
                "name": ep.name or f"{ep.method} {ep.path}",
                "method": ep.method,
                "url": f"{{{{base_url}}}}{ep.path}",
                "description": f"Handler: {ep.handler}\nFile: {ep.file}:{ep.line}"
            }

            # Add parameters
            if ep.parameters:
                params = []
                for p in ep.parameters:
                    if p.get('in') == 'query':
                        params.append({"name": p["name"], "value": "", "disabled": not p.get("required", False)})
                if params:
                    request["parameters"] = params

            # Add body
            if ep.request_body:
                request["body"] = {
                    "mimeType": "application/json",
                    "text": ep.request_body.get("raw", "{}")
                }

            # Add auth
            if ep.auth_required:
                request["authentication"] = {
                    "type": "bearer",
                    "token": "{{api_token}}"
                }

            collection["resources"].append(request)

        return collection

    def to_openapi(self) -> Dict:
        """Generate OpenAPI 3.0 specification."""
        spec = {
            "openapi": "3.0.0",
            "info": {
                "title": "API Documentation",
                "version": "1.0.0",
                "description": "Auto-generated from code analysis"
            },
            "servers": [
                {"url": self.base_url, "description": "API Server"}
            ],
            "paths": {}
        }

        # Group endpoints by path
        for ep in self.endpoints:
            if ep.path not in spec["paths"]:
                spec["paths"][ep.path] = {}

            path_item = spec["paths"][ep.path]

            method_lower = ep.method.lower()
            path_item[method_lower] = {
                "summary": ep.name or f"{ep.method} {ep.path}",
                "description": f"Handler: {ep.handler}\nFile: {ep.file}:{ep.line}",
                "responses": {
                    "200": {
                        "description": "Successful response",
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"}
                            }
                        }
                    }
                }
            }

            # Add parameters
            if ep.parameters:
                path_item[method_lower]["parameters"] = [
                    {
                        "name": p["name"],
                        "in": p.get("in", "query"),
                        "required": p.get("required", False),
                        "schema": p.get("schema", {"type": "string"})
                    }
                    for p in ep.parameters
                ]

            # Add request body
            if ep.request_body:
                path_item[method_lower]["requestBody"] = {
                    "content": {
                        "application/json": {
                            "schema": {"type": "object"}
                        }
                    }
                }

            # Add security
            if ep.auth_required:
                if "components" not in spec:
                    spec["components"] = {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}}
                path_item[method_lower]["security"] = [{"bearerAuth": []}]

        return spec


import os


def main():
    parser = argparse.ArgumentParser(description='Generate API collection from code')
    parser.add_argument('project_path', help='Path to project directory')
    parser.add_argument('--format', choices=['postman', 'insomnia', 'openapi'], default='postman', help='Output format')
    parser.add_argument('--base-url', default='http://localhost:3000', help='Base URL for API')
    parser.add_argument('--output', '-o', help='Output file path')
    args = parser.parse_args()

    generator = APICollectionGenerator(base_url=args.base_url)
    generator.analyze_project(args.project_path)

    if args.format == 'postman':
        output = json.dumps(generator.to_postman(), indent=2)
        ext = '.postman_collection.json'
    elif args.format == 'insomnia':
        output = json.dumps(generator.to_insomnia(), indent=2)
        ext = '.insomnia.json'
    else:
        output = json.dumps(generator.to_openapi(), indent=2)
        ext = '.openapi.json'

    if args.output:
        Path(args.output).write_text(output, encoding='utf-8')
        print(f"API collection saved to: {args.output}")
    else:
        print(output)

    print(f"\nFound {len(generator.endpoints)} API endpoints")


if __name__ == '__main__':
    main()
