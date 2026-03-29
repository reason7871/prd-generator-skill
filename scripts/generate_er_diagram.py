#!/usr/bin/env python3
"""
Generate ER (Entity Relationship) Diagrams from code analysis.
Supports: TypeScript interfaces, Python dataclasses, SQL schemas, Prisma schemas
Output: Mermaid diagram format
"""

import re
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class Entity:
    """Represents a database entity/model."""
    name: str
    fields: List[Dict[str, str]] = field(default_factory=list)
    relations: List[Dict[str, str]] = field(default_factory=list)
    source: str = ""
    line: int = 0


@dataclass
class ERDiagram:
    """Complete ER diagram."""
    entities: List[Entity] = field(default_factory=list)
    relationships: List[Dict[str, str]] = field(default_factory=list)


class ERDiagramGenerator:
    """Generate ER diagrams from various sources."""

    def __init__(self):
        self.diagram = ERDiagram()

    def analyze_file(self, file_path: str, content: str) -> List[Entity]:
        """Analyze a file and extract entities."""
        entities = []
        ext = Path(file_path).suffix.lower()

        if ext in ('.ts', '.tsx'):
            entities.extend(self._extract_typescript_entities(content, file_path))
        elif ext == '.py':
            entities.extend(self._extract_python_entities(content, file_path))
        elif ext == '.sql':
            entities.extend(self._extract_sql_entities(content, file_path))
        elif ext == '.prisma':
            entities.extend(self._extract_prisma_entities(content, file_path))

        return entities

    def _extract_typescript_entities(self, content: str, file_path: str) -> List[Entity]:
        """Extract entities from TypeScript interfaces and types."""
        entities = []

        # Match interfaces
        interface_pattern = r'interface\s+(\w+)(?:\s+extends\s+(\w+))?\s*\{([^}]+)\}'
        for match in re.finditer(interface_pattern, content, re.MULTILINE | re.DOTALL):
            name = match.group(1)
            extends = match.group(2)
            fields_str = match.group(3)

            # Check if this looks like a data model
            if any(kw in name for kw in ['Model', 'Entity', 'Schema', 'Data', 'DTO', 'Input', 'Output', 'Response', 'Request']) or \
               'id' in fields_str.lower() or 'created' in fields_str.lower():

                fields = self._parse_ts_fields(fields_str)
                entity = Entity(
                    name=name,
                    fields=fields,
                    source=file_path,
                    line=content[:match.start()].count('\n') + 1
                )

                if extends:
                    entity.relations.append({
                        'type': 'extends',
                        'target': extends
                    })

                entities.append(entity)

        # Match type definitions
        type_pattern = r'type\s+(\w+)\s*=\s*\{([^}]+)\}'
        for match in re.finditer(type_pattern, content, re.MULTILINE | re.DOTALL):
            name = match.group(1)
            fields_str = match.group(2)

            if any(kw in name for kw in ['Model', 'Entity', 'Schema', 'Data', 'DTO', 'Props']):
                fields = self._parse_ts_fields(fields_str)
                entity = Entity(
                    name=name,
                    fields=fields,
                    source=file_path,
                    line=content[:match.start()].count('\n') + 1
                )
                entities.append(entity)

        return entities

    def _parse_ts_fields(self, fields_str: str) -> List[Dict[str, str]]:
        """Parse TypeScript field definitions."""
        fields = []
        for line in fields_str.split('\n'):
            line = line.strip()
            if not line or line.startswith('//') or line.startswith('/*'):
                continue

            # Match: name: Type or name?: Type
            match = re.match(r'(\w+)(\?)?:\s*(.+?)(?:;|,)?$', line)
            if match:
                name = match.group(1)
                optional = match.group(2) == '?'
                type_hint = match.group(3).strip().rstrip(';,')

                # Detect relations
                is_relation = False
                relation_to = None
                if type_hint.endswith('[]') or type_hint.startswith('Array<'):
                    is_relation = True
                    relation_to = type_hint.replace('[]', '').replace('Array<', '').replace('>', '').strip()
                elif type_hint[0].isupper() and type_hint not in ('String', 'Number', 'Boolean', 'Date'):
                    is_relation = True
                    relation_to = type_hint

                fields.append({
                    'name': name,
                    'type': type_hint,
                    'optional': optional,
                    'primary': name.lower() == 'id',
                    'is_relation': is_relation,
                    'relation_to': relation_to
                })

        return fields[:20]  # Limit fields

    def _extract_python_entities(self, content: str, file_path: str) -> List[Entity]:
        """Extract entities from Python classes (dataclasses, Pydantic, SQLAlchemy)."""
        entities = []

        # Match class definitions
        class_pattern = r'class\s+(\w+)(?:\([^)]+\))?:\s*(?:\n\s+"""([^"]+)""")?'

        for match in re.finditer(class_pattern, content):
            name = match.group(1)
            class_start = match.start()

            # Check if it's a data model class
            bases = match.group(1) if match.group(1) else ''
            is_model = any(kw in name for kw in ['Model', 'Schema', 'Entity', 'Base']) or \
                      'BaseModel' in content[max(0, class_start-100):class_start] or \
                      'dataclass' in content[max(0, class_start-100):class_start]

            if not is_model and 'id' not in content[class_start:class_start+500].lower():
                continue

            # Extract class body
            class_body = self._extract_class_body(content, match.start())
            fields = self._parse_python_fields(class_body)

            if fields:
                entity = Entity(
                    name=name,
                    fields=fields,
                    source=file_path,
                    line=content[:match.start()].count('\n') + 1
                )
                entities.append(entity)

        return entities

    def _extract_class_body(self, content: str, start: int) -> str:
        """Extract the body of a Python class."""
        lines = content[start:].split('\n')
        body_lines = []
        base_indent = None

        for i, line in enumerate(lines[1:], 1):
            if not line.strip():
                body_lines.append(line)
                continue

            current_indent = len(line) - len(line.lstrip())

            if base_indent is None:
                if current_indent > 0:
                    base_indent = current_indent
                    body_lines.append(line)
            elif current_indent >= base_indent:
                body_lines.append(line)
            else:
                break

        return '\n'.join(body_lines)

    def _parse_python_fields(self, class_body: str) -> List[Dict[str, str]]:
        """Parse Python field definitions."""
        fields = []

        # Pydantic/Type hints: name: Type
        type_pattern = r'^\s+(\w+):\s+(?:Optional\[)?(\w+)(?:\])?(?:\s*=\s*([^#\n]+))?'
        for match in re.finditer(type_pattern, class_body, re.MULTILINE):
            name = match.group(1)
            type_hint = match.group(2)
            default = match.group(3)

            fields.append({
                'name': name,
                'type': type_hint,
                'optional': default is not None or 'Optional' in match.group(0),
                'primary': name.lower() == 'id',
            })

        # SQLAlchemy: Column definitions
        column_pattern = r'^\s+(\w+)\s*=\s*Column\(([^)]+)\)'
        for match in re.finditer(column_pattern, class_body, re.MULTILINE):
            name = match.group(1)
            column_def = match.group(2)

            # Extract type
            type_match = re.search(r'(\w+)(?:\([^)]*\))?', column_def)
            type_hint = type_match.group(1) if type_match else 'Unknown'

            fields.append({
                'name': name,
                'type': type_hint,
                'optional': 'nullable=True' in column_def,
                'primary': 'primary_key=True' in column_def,
            })

        return fields[:20]

    def _extract_sql_entities(self, content: str, file_path: str) -> List[Entity]:
        """Extract entities from SQL CREATE TABLE statements."""
        entities = []

        # Match CREATE TABLE
        table_pattern = r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\'"]?(\w+)[\'"]?\s*\(([^;]+)\)'

        for match in re.finditer(table_pattern, content, re.IGNORECASE | re.DOTALL):
            name = match.group(1)
            columns_str = match.group(2)

            fields = []
            for line in columns_str.split(','):
                line = line.strip()
                if not line or line.upper().startswith(('PRIMARY', 'FOREIGN', 'UNIQUE', 'INDEX', 'CONSTRAINT')):
                    continue

                # Parse column definition
                col_match = re.match(r'[\'"]?(\w+)[\'"]?\s+(\w+)(?:\([^)]+\))?(.*)', line)
                if col_match:
                    col_name = col_match.group(1)
                    col_type = col_match.group(2)
                    constraints = col_match.group(3)

                    fields.append({
                        'name': col_name,
                        'type': col_type,
                        'optional': 'NULL' in constraints.upper() and 'NOT NULL' not in constraints.upper(),
                        'primary': 'PRIMARY KEY' in constraints.upper(),
                    })

            if fields:
                entity = Entity(
                    name=name,
                    fields=fields,
                    source=file_path,
                    line=content[:match.start()].count('\n') + 1
                )
                entities.append(entity)

        # Extract foreign key relationships
        fk_pattern = r'FOREIGN\s+KEY\s*\([^)]+\)\s+REFERENCES\s+[\'"]?(\w+)[\'"]?'
        for match in re.finditer(fk_pattern, content, re.IGNORECASE):
            # Add relationship info
            pass  # TODO: Implement relationship tracking

        return entities

    def _extract_prisma_entities(self, content: str, file_path: str) -> List[Entity]:
        """Extract entities from Prisma schema."""
        entities = []

        # Match model definitions
        model_pattern = r'model\s+(\w+)\s*\{([^}]+)\}'

        for match in re.finditer(model_pattern, content, re.MULTILINE | re.DOTALL):
            name = match.group(1)
            fields_str = match.group(2)

            fields = []
            relations = []

            for line in fields_str.split('\n'):
                line = line.strip()
                if not line or line.startswith('//') or line.startswith('@@'):
                    continue

                # Parse field definition
                field_match = re.match(r'(\w+)\s+(\w+)(?:\([^)]*\))?(.*)', line)
                if field_match:
                    field_name = field_match.group(1)
                    field_type = field_match.group(2)
                    attrs = field_match.group(3)

                    # Check for relation
                    is_relation = field_match.group(2)[0].isupper() and field_type not in ('String', 'Int', 'Boolean', 'DateTime', 'Float', 'Json')
                    relation_to = field_type if is_relation else None

                    # Handle array types
                    if field_type.endswith('[]'):
                        is_relation = True
                        relation_to = field_type[:-2]

                    fields.append({
                        'name': field_name,
                        'type': field_type,
                        'optional': '?' in attrs,
                        'primary': '@id' in attrs,
                        'is_relation': is_relation,
                        'relation_to': relation_to
                    })

            if fields:
                entity = Entity(
                    name=name,
                    fields=fields,
                    relations=relations,
                    source=file_path,
                    line=content[:match.start()].count('\n') + 1
                )
                entities.append(entity)

        return entities

    def infer_relationships(self):
        """Infer relationships between entities based on field types."""
        entity_names = {e.name: e for e in self.diagram.entities}

        for entity in self.diagram.entities:
            for field in entity.fields:
                if field.get('is_relation') and field.get('relation_to'):
                    target_name = field['relation_to']
                    if target_name in entity_names:
                        rel_type = 'one-to-many' if field['type'].endswith('[]') else 'many-to-one'
                        self.diagram.relationships.append({
                            'from': entity.name,
                            'to': target_name,
                            'type': rel_type,
                            'label': field['name']
                        })

    def to_mermaid(self) -> str:
        """Generate Mermaid ER diagram."""
        lines = ["erDiagram"]

        # Add entities and their attributes
        for entity in self.diagram.entities:
            for field in entity.fields:
                if not field.get('is_relation'):
                    type_str = field['type'].split('[')[0].split('<')[0][:20]  # Truncate long types
                    key_indicator = " PK" if field.get('primary') else ""
                    lines.append(f"    {entity.name} {{")
                    lines.append(f"        {type_str} {field['name']}{key_indicator}")
                    lines.append("    }")
                    break  # Only show one field per entity in simple view
            else:
                lines.append(f"    {entity.name} {{ }}")

        # Add relationships
        for rel in self.diagram.relationships:
            # Mermaid relationship syntax
            if rel['type'] == 'one-to-many':
                lines.append(f"    {rel['to']} ||--o{{ {rel['from']} : {rel['label']}")
            else:
                lines.append(f"    {rel['to']} ||--o{{ {rel['from']} : {rel['label']}")

        # Add inheritance relationships
        for entity in self.diagram.entities:
            for rel in entity.relations:
                if rel['type'] == 'extends':
                    lines.append(f"    {rel['target']} <|-- {entity.name}")

        return '\n'.join(lines)

    def to_dbml(self) -> str:
        """Generate DBML (Database Markup Language) diagram."""
        lines = []

        for entity in self.diagram.entities:
            lines.append(f"Table {entity.name} {{")
            for field in entity.fields:
                if not field.get('is_relation'):
                    type_str = field['type']
                    constraints = []
                    if field.get('primary'):
                        constraints.append('pk')
                    if not field.get('optional'):
                        constraints.append('not null')

                    constraint_str = ' [' + ', '.join(constraints) + ']' if constraints else ''
                    lines.append(f"    {field['name']} {type_str}{constraint_str}")
            lines.append("}")

        # Add references
        for rel in self.diagram.relationships:
            lines.append(f"Ref: {rel['from']}.{rel['label']} > {rel['to']}.id")

        return '\n'.join(lines)

    def analyze_project(self, project_path: str) -> ERDiagram:
        """Analyze an entire project."""
        project = Path(project_path)
        skip_dirs = {'node_modules', 'venv', '__pycache__', '.git', 'dist', 'build', '.next'}

        for root, dirs, files in os.walk(project):
            dirs[:] = [d for d in dirs if d not in skip_dirs]

            for file in files:
                ext = Path(file).suffix.lower()
                if ext in ('.ts', '.tsx', '.py', '.sql', '.prisma'):
                    file_path = Path(root) / file
                    try:
                        content = file_path.read_text(encoding='utf-8', errors='ignore')
                        entities = self.analyze_file(str(file_path.relative_to(project)), content)
                        self.diagram.entities.extend(entities)
                    except Exception as e:
                        print(f"Warning: Could not analyze {file_path}: {e}")

        # Infer relationships after all entities are collected
        self.infer_relationships()

        return self.diagram


import os


def main():
    parser = argparse.ArgumentParser(description='Generate ER diagram from code')
    parser.add_argument('project_path', help='Path to project directory')
    parser.add_argument('--format', choices=['mermaid', 'dbml'], default='mermaid', help='Output format')
    parser.add_argument('--output', '-o', help='Output file path')
    args = parser.parse_args()

    generator = ERDiagramGenerator()
    diagram = generator.analyze_project(args.project_path)

    if args.format == 'mermaid':
        output = generator.to_mermaid()
    else:
        output = generator.to_dbml()

    if args.output:
        Path(args.output).write_text(output, encoding='utf-8')
        print(f"ER diagram saved to: {args.output}")
    else:
        print(output)


if __name__ == '__main__':
    main()
