#!/usr/bin/env python3
"""
Enhanced Codebase Analyzer for PRD Generation
Supports: API extraction, data model inference, dependency analysis, component mapping
"""

import os
import json
import re
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, asdict, field
from collections import defaultdict
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class APIEndpoint:
    """Represents an API endpoint."""
    method: str
    path: str
    file: str
    line: int
    handler: str
    parameters: List[Dict[str, str]] = field(default_factory=list)
    request_body: Optional[str] = None
    response_type: Optional[str] = None
    description: Optional[str] = None
    auth_required: bool = False


@dataclass
class DataModel:
    """Represents a data model/schema."""
    name: str
    file: str
    line: int
    type: str  # 'interface', 'class', 'type', 'schema'
    fields: List[Dict[str, str]] = field(default_factory=list)
    extends: Optional[str] = None
    description: Optional[str] = None


@dataclass
class Component:
    """Represents a frontend component."""
    name: str
    file: str
    line: int
    type: str  # 'function', 'class'
    props: List[str] = field(default_factory=list)
    state: List[str] = field(default_factory=list)
    hooks: List[str] = field(default_factory=list)
    description: Optional[str] = None


@dataclass
class ModuleInfo:
    """Information about a code module."""
    name: str
    path: str
    type: str  # 'frontend', 'backend', 'shared', 'config'
    files: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """Complete analysis result."""
    project_path: str
    project_name: str
    project_type: str
    tech_stack: Dict[str, List[str]] = field(default_factory=dict)
    apis: List[Dict] = field(default_factory=list)
    data_models: List[Dict] = field(default_factory=list)
    components: List[Dict] = field(default_factory=list)
    modules: Dict[str, Dict] = field(default_factory=dict)
    dependencies: Dict[str, str] = field(default_factory=dict)
    dev_dependencies: Dict[str, str] = field(default_factory=dict)
    file_stats: Dict[str, int] = field(default_factory=dict)
    entry_points: List[str] = field(default_factory=list)
    config_files: List[str] = field(default_factory=list)


class CodebaseAnalyzer:
    """Enhanced codebase analyzer with deep inspection capabilities."""

    LANGUAGE_PATTERNS = {
        'typescript': {
            'extensions': ['.ts', '.tsx'],
            'api_patterns': [
                r'(GET|POST|PUT|DELETE|PATCH)\s*\(\s*[\'"]([^\'"]+)[\'"]',
                r'@(Get|Post|Put|Delete|Patch)\s*\(\s*[\'"]([^\'"]+)[\'"]',
                r'app\.(get|post|put|delete|patch)\s*\(\s*[\'"]([^\'"]+)[\'"]',
                r'router\.(get|post|put|delete|patch)\s*\(\s*[\'"]([^\'"]+)[\'"]',
            ],
            'interface_pattern': r'interface\s+(\w+)(?:\s+extends\s+(\w+))?\s*\{([^}]+)\}',
            'type_pattern': r'type\s+(\w+)\s*=\s*([^;]+)',
            'class_pattern': r'class\s+(\w+)(?:\s+extends\s+(\w+))?',
            'function_pattern': r'(?:export\s+)?(?:async\s+)?function\s+(\w+)',
            'arrow_function': r'(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[^=])\s*=>',
            'import_pattern': r'import\s+(?:\{[^}]+\}|\*\s+as\s+\w+|\w+)\s+from\s+[\'"]([^\'"]+)[\'"]',
            'export_pattern': r'export\s+(?:default\s+)?(?:const|function|class|interface|type)\s+(\w+)',
        },
        'javascript': {
            'extensions': ['.js', '.jsx'],
            'api_patterns': [
                r'app\.(get|post|put|delete|patch)\s*\(\s*[\'"]([^\'"]+)[\'"]',
                r'router\.(get|post|put|delete|patch)\s*\(\s*[\'"]([^\'"]+)[\'"]',
            ],
            'class_pattern': r'class\s+(\w+)',
            'function_pattern': r'(?:export\s+)?function\s+(\w+)',
            'import_pattern': r'(?:import\s+.*?from\s+[\'"]([^\'"]+)[\'"])|(?:require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\))',
        },
        'python': {
            'extensions': ['.py'],
            'api_patterns': [
                r'@(app|router)\.(get|post|put|delete|patch)\s*\(\s*[\'"]([^\'"]+)[\'"]',
                r'@route\.\w+\s*\(\s*[\'"]([^\'"]+)[\'"]',
            ],
            'class_pattern': r'class\s+(\w+)(?:\([^)]+\))?:',
            'function_pattern': r'def\s+(\w+)\s*\(',
            'import_pattern': r'^(?:from\s+(\S+)\s+)?import\s+(.+)$',
        },
        'go': {
            'extensions': ['.go'],
            'api_patterns': [
                r'(r\.)?(HandleFunc|Handle)\s*\(\s*[\'"]([^\'"]+)[\'"]',
            ],
            'struct_pattern': r'type\s+(\w+)\s+struct\s*\{',
            'func_pattern': r'func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(',
        },
    }

    FRAMEWORK_SIGNATURES = {
        'nextjs': ['next', 'next/navigation', 'next/link', 'next/image'],
        'react': ['react', 'react-dom'],
        'vue': ['vue', '@vue/'],
        'angular': ['@angular/'],
        'express': ['express'],
        'fastapi': ['fastapi'],
        'django': ['django'],
        'flask': ['flask'],
        'nestjs': ['@nestjs/'],
    }

    def __init__(self, project_path: str, deep: bool = False):
        self.project_path = Path(project_path)
        self.deep = deep
        self.result = AnalysisResult(
            project_path=str(project_path),
            project_name=self.project_path.name,
            project_type='unknown'
        )
        self._files_cache: Dict[str, str] = {}

    def analyze(self) -> AnalysisResult:
        """Run the full analysis."""
        logger.info(f"Analyzing project: {self.project_path}")

        # Phase 1: Project structure
        self._detect_project_type()
        self._scan_dependencies()

        # Phase 2: File scanning
        self._scan_all_files()

        # Phase 3: Deep analysis (if enabled)
        if self.deep:
            self._extract_apis()
            self._extract_data_models()
            self._extract_components()
            self._analyze_dependencies()

        # Phase 4: Statistics
        self._calculate_stats()

        return self.result

    def _detect_project_type(self):
        """Detect the type of project."""
        path = self.project_path

        # Check for framework configs
        if (path / 'next.config.js').exists() or (path / 'next.config.mjs').exists():
            self.result.project_type = 'nextjs'
        elif (path / 'nuxt.config.js').exists():
            self.result.project_type = 'nuxt'
        elif (path / 'angular.json').exists():
            self.result.project_type = 'angular'
        elif (path / 'vue.config.js').exists():
            self.result.project_type = 'vue'
        elif (path / 'requirements.txt').exists():
            content = (path / 'requirements.txt').read_text(encoding='utf-8', errors='ignore').lower()
            if 'fastapi' in content:
                self.result.project_type = 'fastapi'
            elif 'django' in content:
                self.result.project_type = 'django'
            elif 'flask' in content:
                self.result.project_type = 'flask'
            else:
                self.result.project_type = 'python'
        elif (path / 'go.mod').exists():
            self.result.project_type = 'go'
        elif (path / 'package.json').exists():
            self.result.project_type = 'nodejs'

        logger.info(f"Detected project type: {self.result.project_type}")

    def _scan_dependencies(self):
        """Scan package dependencies."""
        # Node.js / JavaScript
        pkg_json = self.project_path / 'package.json'
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text(encoding='utf-8'))
                self.result.dependencies = data.get('dependencies', {})
                self.result.dev_dependencies = data.get('devDependencies', {})

                # Detect frameworks from dependencies
                for framework, signatures in self.FRAMEWORK_SIGNATURES.items():
                    for sig in signatures:
                        if sig in self.result.dependencies or sig in self.result.dev_dependencies:
                            self.result.tech_stack.setdefault('frameworks', []).append(framework)
                            break

                if self.result.dependencies:
                    self.result.tech_stack['runtime'] = ['Node.js']
            except Exception as e:
                logger.warning(f"Failed to parse package.json: {e}")

        # Python
        req_txt = self.project_path / 'requirements.txt'
        if req_txt.exists():
            self.result.tech_stack['runtime'] = ['Python']
            content = req_txt.read_text(encoding='utf-8', errors='ignore').lower()
            for fw in ['django', 'flask', 'fastapi', 'requests', 'numpy', 'pandas']:
                if fw in content:
                    self.result.tech_stack.setdefault('libraries', []).append(fw)

        # Go
        go_mod = self.project_path / 'go.mod'
        if go_mod.exists():
            self.result.tech_stack['runtime'] = ['Go']
            content = go_mod.read_text(encoding='utf-8', errors='ignore')
            deps = re.findall(r'require\s+(\S+)\s+v[\d.]+', content)
            self.result.tech_stack.setdefault('libraries', []).extend(deps[:10])

    def _scan_all_files(self):
        """Scan all source files in the project."""
        skip_dirs = {'node_modules', 'venv', '__pycache__', '.git', 'dist', 'build', '.next', 'coverage', '.idea', '.vscode'}

        for root, dirs, files in os.walk(self.project_path):
            # Filter directories
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith('.')]

            for file in files:
                file_path = Path(root) / file
                ext = file_path.suffix.lower()

                # Determine file type
                file_type = self._get_file_type(ext)
                if file_type:
                    rel_path = str(file_path.relative_to(self.project_path))
                    self.result.file_stats[file_type] = self.result.file_stats.get(file_type, 0) + 1

                    # Cache file content for deep analysis
                    if self.deep and file_type in ('typescript', 'javascript', 'python', 'go'):
                        try:
                            self._files_cache[rel_path] = file_path.read_text(encoding='utf-8', errors='ignore')
                        except Exception:
                            pass

                    # Identify entry points
                    if file in ('index.ts', 'index.js', 'main.ts', 'main.js', 'main.go', 'app.py', '__init__.py'):
                        self.result.entry_points.append(rel_path)

                    # Identify config files
                    if file.endswith(('.config.js', '.config.ts', '.config.mjs', '.json', '.yaml', '.yml')):
                        if 'node_modules' not in str(file_path):
                            self.result.config_files.append(rel_path)

    def _get_file_type(self, ext: str) -> Optional[str]:
        """Get file type from extension."""
        type_map = {
            '.ts': 'typescript', '.tsx': 'typescript',
            '.js': 'javascript', '.jsx': 'javascript', '.mjs': 'javascript',
            '.py': 'python',
            '.go': 'go',
            '.java': 'java',
            '.rb': 'ruby',
            '.php': 'php',
            '.vue': 'vue',
            '.svelte': 'svelte',
            '.css': 'css', '.scss': 'css', '.less': 'css',
            '.html': 'html',
            '.json': 'json',
            '.md': 'markdown',
            '.sql': 'sql',
        }
        return type_map.get(ext)

    def _extract_apis(self):
        """Extract API endpoints from the codebase."""
        for file_path, content in self._files_cache.items():
            # Check if this is an API route file
            if 'api' in file_path.lower() or 'route' in file_path.lower() or 'controller' in file_path.lower():
                lang = self._get_language(file_path)
                if lang and lang in self.LANGUAGE_PATTERNS:
                    patterns = self.LANGUAGE_PATTERNS[lang].get('api_patterns', [])
                    for pattern in patterns:
                        matches = re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE)
                        for match in matches:
                            groups = match.groups()
                            method = groups[0].upper() if groups[0] else 'GET'
                            path = groups[1] if len(groups) > 1 else groups[0]

                            endpoint = APIEndpoint(
                                method=method.upper(),
                                path=path,
                                file=file_path,
                                line=content[:match.start()].count('\n') + 1,
                                handler=self._extract_handler_name(content, match.start())
                            )
                            self.result.apis.append(asdict(endpoint))

        logger.info(f"Extracted {len(self.result.apis)} API endpoints")

    def _extract_handler_name(self, content: str, position: int) -> str:
        """Try to extract the handler function name near a position."""
        # Look for nearby function definition
        nearby = content[max(0, position - 200):position + 500]
        func_match = re.search(r'(?:async\s+)?function\s+(\w+)|(?:const|let)\s+(\w+)\s*=', nearby)
        if func_match:
            return func_match.group(1) or func_match.group(2)
        return 'anonymous'

    def _extract_data_models(self):
        """Extract data models/interfaces from the codebase."""
        for file_path, content in self._files_cache.items():
            lang = self._get_language(file_path)
            if not lang:
                continue

            patterns = self.LANGUAGE_PATTERNS.get(lang, {})

            # TypeScript interfaces
            if 'interface_pattern' in patterns:
                matches = re.finditer(patterns['interface_pattern'], content, re.MULTILINE | re.DOTALL)
                for match in matches:
                    name = match.group(1)
                    extends = match.group(2) if len(match.groups()) > 1 else None
                    fields_str = match.group(3) if len(match.groups()) > 2 else ''

                    fields = self._parse_interface_fields(fields_str)

                    model = DataModel(
                        name=name,
                        file=file_path,
                        line=content[:match.start()].count('\n') + 1,
                        type='interface',
                        fields=fields,
                        extends=extends
                    )
                    self.result.data_models.append(asdict(model))

            # TypeScript types
            if 'type_pattern' in patterns:
                matches = re.finditer(patterns['type_pattern'], content, re.MULTILINE)
                for match in matches:
                    model = DataModel(
                        name=match.group(1),
                        file=file_path,
                        line=content[:match.start()].count('\n') + 1,
                        type='type',
                        description=match.group(2)[:100] if match.group(2) else None
                    )
                    self.result.data_models.append(asdict(model))

            # Python classes (potential data models)
            if lang == 'python':
                matches = re.finditer(r'class\s+(\w+)(?:\([^)]+\))?:\s*(?:\n\s+"""([^"]+)""")?', content)
                for match in matches:
                    # Check if it looks like a data model
                    class_name = match.group(1)
                    if any(kw in class_name for kw in ['Model', 'Schema', 'Data', 'Config', 'Request', 'Response']):
                        model = DataModel(
                            name=class_name,
                            file=file_path,
                            line=content[:match.start()].count('\n') + 1,
                            type='class',
                            description=match.group(2)[:100] if match.group(2) else None
                        )
                        self.result.data_models.append(asdict(model))

        logger.info(f"Extracted {len(self.result.data_models)} data models")

    def _parse_interface_fields(self, fields_str: str) -> List[Dict[str, str]]:
        """Parse interface fields from string."""
        fields = []
        for line in fields_str.split('\n'):
            line = line.strip()
            if ':' in line and not line.startswith('//') and not line.startswith('/*'):
                parts = line.split(':', 1)
                if len(parts) == 2:
                    name = parts[0].strip().rstrip('?')
                    type_hint = parts[1].strip().rstrip(';,')
                    if name and not name.startswith('//'):
                        fields.append({'name': name, 'type': type_hint})
        return fields[:20]  # Limit to 20 fields

    def _extract_components(self):
        """Extract frontend components."""
        for file_path, content in self._files_cache.items():
            if not file_path.endswith(('.tsx', '.jsx', '.vue', '.svelte')):
                continue

            # React function components
            func_matches = re.finditer(
                r'(?:export\s+(?:default\s+)?)?(?:function|const)\s+(\w+)\s*(?:=\s*(?:\([^)]*\)|[^=])\s*=>|\([^)]*\)\s*(?::\s*[^{]+)?\s*\{)',
                content
            )
            for match in func_matches:
                if match.group(1)[0].isupper():  # Component names start with uppercase
                    component = Component(
                        name=match.group(1),
                        file=file_path,
                        line=content[:match.start()].count('\n') + 1,
                        type='function',
                        props=self._extract_props(content, match.start()),
                        hooks=self._extract_hooks(content, match.start())
                    )
                    self.result.components.append(asdict(component))

        logger.info(f"Extracted {len(self.result.components)} components")

    def _extract_props(self, content: str, position: int) -> List[str]:
        """Extract component props."""
        nearby = content[position:position + 500]
        props_match = re.search(r'\{\s*(\w+Props)\s*\}', nearby)
        if props_match:
            return [props_match.group(1)]
        return []

    def _extract_hooks(self, content: str, position: int) -> List[str]:
        """Extract React hooks used in component."""
        nearby = content[position:position + 2000]
        hooks = re.findall(r'(use[A-Z]\w+)\s*(?:\(|<)', nearby)
        return list(set(hooks))[:10]

    def _analyze_dependencies(self):
        """Analyze internal module dependencies."""
        for file_path, content in self._files_cache.items():
            rel_path = Path(file_path)
            module_name = rel_path.parent.name or 'root'

            if module_name not in self.result.modules:
                self.result.modules[module_name] = {
                    'name': module_name,
                    'path': str(rel_path.parent),
                    'files': [],
                    'imports': [],
                    'exports': []
                }

            self.result.modules[module_name]['files'].append(rel_path.name)

            # Extract imports
            imports = re.findall(r'(?:import\s+.*?from\s+[\'"]([^\'"]+)[\'"])', content)
            self.result.modules[module_name]['imports'].extend(imports[:20])

            # Extract exports
            exports = re.findall(r'export\s+(?:default\s+)?(?:const|function|class)\s+(\w+)', content)
            self.result.modules[module_name]['exports'].extend(exports[:10])

    def _get_language(self, file_path: str) -> Optional[str]:
        """Get programming language from file path."""
        ext = Path(file_path).suffix.lower()
        for lang, config in self.LANGUAGE_PATTERNS.items():
            if ext in config.get('extensions', []):
                return lang
        return None

    def _calculate_stats(self):
        """Calculate final statistics."""
        total_files = sum(self.result.file_stats.values())
        self.result.file_stats['total'] = total_files

    def to_json(self) -> str:
        """Export analysis result as JSON."""
        return json.dumps(asdict(self.result), indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description='Analyze codebase for PRD generation')
    parser.add_argument('project_path', help='Path to the project directory')
    parser.add_argument('--deep', action='store_true', help='Enable deep analysis')
    parser.add_argument('--output', '-o', help='Output JSON file path')
    args = parser.parse_args()

    analyzer = CodebaseAnalyzer(args.project_path, deep=args.deep)
    result = analyzer.analyze()

    output = analyzer.to_json()

    if args.output:
        Path(args.output).write_text(output, encoding='utf-8')
        logger.info(f"Analysis saved to: {args.output}")
    else:
        print(output)


if __name__ == '__main__':
    main()
