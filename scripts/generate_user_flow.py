#!/usr/bin/env python3
"""
Generate User Flow Diagrams from code analysis.
Analyzes page routes, components, and user interactions to generate flow diagrams.
"""

import re
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class FlowNode:
    """Represents a node in the user flow."""
    id: str
    type: str  # 'page', 'action', 'decision', 'api', 'external'
    label: str
    path: str = ""
    file: str = ""
    line: int = 0


@dataclass
class FlowEdge:
    """Represents an edge between flow nodes."""
    from_id: str
    to_id: str
    label: str = ""
    condition: str = ""


@dataclass
class UserFlow:
    """Complete user flow diagram."""
    name: str
    nodes: List[FlowNode] = field(default_factory=list)
    edges: List[FlowEdge] = field(default_factory=list)
    entry_points: List[str] = field(default_factory=list)


class UserFlowGenerator:
    """Generate user flow diagrams from code."""

    def __init__(self):
        self.flows: Dict[str, UserFlow] = {}
        self.all_nodes: Dict[str, FlowNode] = {}
        self.all_edges: List[FlowEdge] = []

    def analyze_file(self, file_path: str, content: str):
        """Analyze a file for user flow elements."""
        ext = Path(file_path).suffix.lower()

        if ext in ('.tsx', '.jsx'):
            self._extract_react_flow(file_path, content)
        elif ext in ('.ts', '.js'):
            if 'api' in file_path.lower() or 'route' in file_path.lower():
                self._extract_api_flow(file_path, content)
        elif ext == '.vue':
            self._extract_vue_flow(file_path, content)

    def _extract_react_flow(self, file_path: str, content: str):
        """Extract user flow from React components."""
        # Detect page components
        is_page = 'page' in file_path.lower() or 'route' in file_path.lower()

        # Extract component name
        component_match = re.search(
            r'(?:export\s+(?:default\s+)?(?:function|const)\s+(\w+)|(?:function|const)\s+(\w+)\s*[=\(])',
            content
        )
        component_name = component_match.group(1) or component_match.group(2) if component_match else Path(file_path).stem

        # Create node for this page/component
        node_id = f"page_{component_name}"
        node = FlowNode(
            id=node_id,
            type='page' if is_page else 'action',
            label=self._format_label(component_name),
            file=file_path,
            line=1
        )

        # Extract route path if it's a page
        if is_page:
            node.path = self._extract_route_path(file_path)

        self.all_nodes[node_id] = node

        # Extract navigation actions
        self._extract_navigation(content, node_id)

        # Extract form submissions
        self._extract_form_actions(content, node_id)

        # Extract API calls
        self._extract_api_calls(content, node_id)

        # Extract conditional rendering (decisions)
        self._extract_decisions(content, node_id)

    def _extract_route_path(self, file_path: str) -> str:
        """Extract route path from file path."""
        # Next.js App Router
        if '/app/' in file_path:
            parts = file_path.split('/app/')[-1].split('/')
            path_parts = []
            for part in parts:
                if part.startswith('(') and part.endswith(')'):
                    continue  # Skip route groups
                if part in ('page.tsx', 'page.js', 'layout.tsx', 'layout.js'):
                    continue
                if part == 'page.tsx' or part == 'page.js':
                    break
                # Handle dynamic routes
                if part.startswith('[') and part.endswith(']'):
                    path_parts.append(':' + part[1:-1])
                else:
                    path_parts.append(part)
            return '/' + '/'.join(path_parts) if path_parts else '/'

        # Pages router
        if '/pages/' in file_path:
            path = file_path.split('/pages/')[-1]
            path = path.replace('/index.tsx', '').replace('/index.js', '')
            path = path.replace('.tsx', '').replace('.js', '')
            return '/' + path if path else '/'

        return '/'

    def _extract_navigation(self, content: str, from_node: str):
        """Extract navigation actions (Link, router.push, etc.)."""
        patterns = [
            (r'<Link\s+href=[\'"]([^\'"]+)[\'"]', 'Navigate'),
            (r'router\.push\([\'"]([^\'"]+)[\'"]\)', 'Redirect'),
            (r'router\.replace\([\'"]([^\'"]+)[\'"]\)', 'Replace'),
            (r'href=[\'"]([^\'"]+)[\'"]', 'Link'),
            (r'window\.location\.href\s*=\s*[\'"]([^\'"]+)[\'"]', 'Navigate'),
        ]

        for pattern, action_type in patterns:
            for match in re.finditer(pattern, content):
                target_path = match.group(1)
                if target_path.startswith('http') or target_path.startswith('#'):
                    continue

                target_id = f"page_{target_path.replace('/', '_').strip('_') or 'home'}"

                if target_id not in self.all_nodes:
                    self.all_nodes[target_id] = FlowNode(
                        id=target_id,
                        type='page',
                        label=self._format_label(target_path),
                        path=target_path
                    )

                self.all_edges.append(FlowEdge(
                    from_id=from_node,
                    to_id=target_id,
                    label=action_type
                ))

    def _extract_form_actions(self, content: str, from_node: str):
        """Extract form submission actions."""
        patterns = [
            (r'onSubmit\s*=\s*\{[^}]*fetch\([\'"]([^\'"]+)[\'"]', 'Submit Form'),
            (r'form.*?action=[\'"]([^\'"]+)[\'"]', 'Form Submit'),
            (r'mutate\([^)]*\)', 'Mutation'),
        ]

        for pattern, action_type in patterns:
            for match in re.finditer(pattern, content, re.DOTALL):
                api_path = match.group(1) if match.groups() else '/api/submit'
                api_id = f"api_{api_path.replace('/', '_').strip('_')}"

                if api_id not in self.all_nodes:
                    self.all_nodes[api_id] = FlowNode(
                        id=api_id,
                        type='api',
                        label=f"API: {api_path}",
                        path=api_path
                    )

                self.all_edges.append(FlowEdge(
                    from_id=from_node,
                    to_id=api_id,
                    label=action_type
                ))

    def _extract_api_calls(self, content: str, from_node: str):
        """Extract API calls."""
        patterns = [
            (r'fetch\([\'"]([^\'"]+)[\'"]', 'Fetch'),
            (r'axios\.(get|post|put|delete)\([\'"]([^\'"]+)[\'"]', 'API Call'),
            (r'useQuery\([\'"]([^\'"]+)[\'"]', 'Query'),
            (r'useMutation\([\'"]([^\'"]+)[\'"]', 'Mutation'),
        ]

        for pattern, action_type in patterns:
            for match in re.finditer(pattern, content):
                groups = match.groups()
                if len(groups) > 1:
                    api_path = groups[1]  # For axios.method(path)
                else:
                    api_path = groups[0]

                if api_path.startswith('http'):
                    # External API
                    ext_id = f"ext_{hashlib.md5(api_path.encode()).hexdigest()[:8]}"
                    if ext_id not in self.all_nodes:
                        self.all_nodes[ext_id] = FlowNode(
                            id=ext_id,
                            type='external',
                            label=f"External: {api_path[:30]}..."
                        )
                    target_id = ext_id
                else:
                    api_id = f"api_{api_path.replace('/', '_').strip('_')}"
                    if api_id not in self.all_nodes:
                        self.all_nodes[api_id] = FlowNode(
                            id=api_id,
                            type='api',
                            label=f"API: {api_path}",
                            path=api_path
                        )
                    target_id = api_id

                self.all_edges.append(FlowEdge(
                    from_id=from_node,
                    to_id=target_id,
                    label=action_type
                ))

    def _extract_decisions(self, content: str, from_node: str):
        """Extract conditional rendering as decisions."""
        # Simple condition patterns
        patterns = [
            (r'\{([^}]+)\s*\?\s*<([^>]+)>', 'Conditional'),
            (r'if\s*\(([^)]+)\)\s*\{', 'If'),
        ]

        for pattern, decision_type in patterns:
            for match in re.finditer(pattern, content):
                condition = match.group(1).strip()[:50]
                if len(condition) > 5:
                    decision_id = f"decision_{hash(condition) % 10000}"

                    if decision_id not in self.all_nodes:
                        self.all_nodes[decision_id] = FlowNode(
                            id=decision_id,
                            type='decision',
                            label=f"{condition}?",
                            file=from_node.replace('page_', ''),
                            line=content[:match.start()].count('\n') + 1
                        )

                    self.all_edges.append(FlowEdge(
                        from_id=from_node,
                        to_id=decision_id,
                        label=decision_type
                    ))

    def _extract_api_flow(self, file_path: str, content: str):
        """Extract flow from API routes."""
        # Extract HTTP methods and paths
        methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']

        for method in methods:
            if re.search(rf'(export\s+async\s+function\s+{method}|{method}\s*\()', content):
                api_path = self._extract_route_path(file_path)
                api_id = f"api_{api_path.replace('/', '_').strip('_')}"

                if api_id not in self.all_nodes:
                    self.all_nodes[api_id] = FlowNode(
                        id=api_id,
                        type='api',
                        label=f"{method} {api_path}",
                        path=api_path,
                        file=file_path
                    )

                # Check for redirects in API
                redirect_match = re.search(r'redirect\([\'"]([^\'"]+)[\'"]\)', content)
                if redirect_match:
                    target_path = redirect_match.group(1)
                    target_id = f"page_{target_path.replace('/', '_').strip('_')}"
                    self.all_edges.append(FlowEdge(
                        from_id=api_id,
                        to_id=target_id,
                        label="Redirect"
                    ))

    def _extract_vue_flow(self, file_path: str, content: str):
        """Extract user flow from Vue components."""
        # Similar to React but with Vue-specific patterns
        self._extract_react_flow(file_path, content)  # Base extraction

        # Vue Router patterns
        router_patterns = [
            (r'this\.\$router\.push\([\'"]([^\'"]+)[\'"]\)', 'Navigate'),
            (r'<router-link\s+to=[\'"]([^\'"]+)[\'"]', 'Link'),
        ]

        for pattern, action_type in router_patterns:
            for match in re.finditer(pattern, content):
                target_path = match.group(1)
                target_id = f"page_{target_path.replace('/', '_').strip('_')}"

                if target_id not in self.all_nodes:
                    self.all_nodes[target_id] = FlowNode(
                        id=target_id,
                        type='page',
                        label=self._format_label(target_path),
                        path=target_path
                    )

    def _format_label(self, name: str) -> str:
        """Format a label for display."""
        # Clean up the name
        name = name.replace('-', ' ').replace('_', ' ').replace('/', '')
        name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)  # camelCase to spaces
        return name.strip().title()[:30]

    def analyze_project(self, project_path: str) -> Dict[str, UserFlow]:
        """Analyze an entire project."""
        project = Path(project_path)
        skip_dirs = {'node_modules', 'venv', '__pycache__', '.git', 'dist', 'build', '.next'}

        for root, dirs, files in os.walk(project):
            dirs[:] = [d for d in dirs if d not in skip_dirs]

            for file in files:
                ext = Path(file).suffix.lower()
                if ext in ('.tsx', '.jsx', '.ts', '.js', '.vue'):
                    file_path = Path(root) / file
                    try:
                        content = file_path.read_text(encoding='utf-8', errors='ignore')
                        rel_path = str(file_path.relative_to(project))
                        self.analyze_file(rel_path, content)
                    except Exception as e:
                        print(f"Warning: Could not analyze {file_path}: {e}")

        # Create main flow
        self.flows['main'] = UserFlow(
            name='Main User Flow',
            nodes=list(self.all_nodes.values()),
            edges=self.all_edges,
            entry_points=['page_Home', 'page_']  # Common entry points
        )

        return self.flows

    def to_mermaid(self) -> str:
        """Generate Mermaid flowchart."""
        lines = ["flowchart TD"]

        # Add nodes
        for node in self.all_nodes.values():
            shape_map = {
                'page': ('[', ']'),      # Rectangle
                'action': ('(', ')'),     # Rounded
                'decision': ('{', '}'),   # Diamond
                'api': ('[[', ']]'),      # Subroutine
                'external': ('>', ']'),   # Async
            }
            shape = shape_map.get(node.type, ('[', ']'))
            lines.append(f"    {node.id}{shape[0]}{node.label}{shape[1]}")

        # Add edges
        for edge in self.all_edges:
            label = f"|{edge.label}|" if edge.label else ""
            lines.append(f"    {edge.from_id} -->{label} {edge.to_id}")

        return '\n'.join(lines)

    def to_plantuml(self) -> str:
        """Generate PlantUML activity diagram."""
        lines = ["@startuml", "skinparam activityBackgroundColor #FFFFFF"]

        # Add start
        lines.append("start")

        # Track visited nodes to avoid duplicates
        visited = set()

        def add_node(node: FlowNode, indent: str = ""):
            if node.id in visited:
                return
            visited.add(node.id)

            if node.type == 'decision':
                lines.append(f"{indent}if ({node.label}) then (yes)")
                # Find edges from this node
                for edge in self.all_edges:
                    if edge.from_id == node.id:
                        target = self.all_nodes.get(edge.to_id)
                        if target:
                            add_node(target, indent + "  ")
                lines.append(f"{indent}else (no)")
                lines.append(f"{indent}endif")
            elif node.type == 'api':
                lines.append(f"{indent}:{node.label};")
            elif node.type == 'page':
                lines.append(f"{indent}:{node.label};")
            else:
                lines.append(f"{indent}:{node.label};")

        # Find entry points and trace flows
        entry_nodes = [n for n in self.all_nodes.values() if n.type == 'page' and (not n.path or n.path == '/')]

        for entry in entry_nodes[:1]:  # Start with first entry point
            add_node(entry)

        lines.append("stop")
        lines.append("@enduml")

        return '\n'.join(lines)

    def to_json(self) -> Dict:
        """Generate JSON representation."""
        return {
            'flows': {
                name: {
                    'name': flow.name,
                    'nodes': [
                        {
                            'id': n.id,
                            'type': n.type,
                            'label': n.label,
                            'path': n.path,
                            'file': n.file,
                            'line': n.line
                        }
                        for n in flow.nodes
                    ],
                    'edges': [
                        {
                            'from': e.from_id,
                            'to': e.to_id,
                            'label': e.label,
                            'condition': e.condition
                        }
                        for e in flow.edges
                    ],
                    'entryPoints': flow.entry_points
                }
                for name, flow in self.flows.items()
            }
        }


import os
import hashlib


def main():
    parser = argparse.ArgumentParser(description='Generate user flow diagrams from code')
    parser.add_argument('project_path', help='Path to project directory')
    parser.add_argument('--format', choices=['mermaid', 'plantuml', 'json'], default='mermaid', help='Output format')
    parser.add_argument('--output', '-o', help='Output file path')
    args = parser.parse_args()

    generator = UserFlowGenerator()
    generator.analyze_project(args.project_path)

    if args.format == 'mermaid':
        output = generator.to_mermaid()
    elif args.format == 'plantuml':
        output = generator.to_plantuml()
    else:
        output = json.dumps(generator.to_json(), indent=2)

    if args.output:
        Path(args.output).write_text(output, encoding='utf-8')
        print(f"User flow diagram saved to: {args.output}")
    else:
        print(output)

    print(f"\nFound {len(generator.all_nodes)} nodes and {len(generator.all_edges)} edges")


if __name__ == '__main__':
    main()
