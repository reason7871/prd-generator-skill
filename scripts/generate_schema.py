#!/usr/bin/env python3
"""
Generate Database Schemas from code analysis.
Supports: TypeScript interfaces → SQL, TypeScript interfaces → Prisma Schema
"""

import re
import argparse
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class SchemaField:
    """Represents a database field."""
    name: str
    type: str
    nullable: bool = False
    primary_key: bool = False
    foreign_key: Optional[str] = None
    default: Optional[str] = None
    unique: bool = False
    index: bool = False


@dataclass
class SchemaModel:
    """Represents a database model/table."""
    name: str
    fields: List[SchemaField] = field(default_factory=list)
    indexes: List[List[str]] = field(default_factory=list)
    source_file: str = ""


class SchemaGenerator:
    """Generate database schemas from code analysis."""

    # Type mappings
    TS_TO_SQL = {
        'string': 'VARCHAR(255)',
        'number': 'INTEGER',
        'boolean': 'BOOLEAN',
        'Date': 'TIMESTAMP',
        'boolean': 'BOOLEAN',
        'object': 'JSONB',
        'any': 'JSONB',
        'unknown': 'JSONB',
        'string[]': 'TEXT[]',
        'number[]': 'INTEGER[]',
    }

    TS_TO_PRISMA = {
        'string': 'String',
        'number': 'Int',
        'boolean': 'Boolean',
        'Date': 'DateTime',
        'object': 'Json',
        'any': 'Json',
        'unknown': 'Json',
        'string[]': 'String[]',
        'number[]': 'Int[]',
    }

    PYTHON_TO_SQL = {
        'str': 'VARCHAR(255)',
        'int': 'INTEGER',
        'float': 'REAL',
        'bool': 'BOOLEAN',
        'datetime': 'TIMESTAMP',
        'date': 'DATE',
        'dict': 'JSONB',
        'list': 'JSONB',
        'Any': 'JSONB',
    }

    PYTHON_TO_PRISMA = {
        'str': 'String',
        'int': 'Int',
        'float': 'Float',
        'bool': 'Boolean',
        'datetime': 'DateTime',
        'date': 'DateTime',
        'dict': 'Json',
        'list': 'Json',
        'Any': 'Json',
    }

    def __init__(self, dialect: str = 'postgresql'):
        self.dialect = dialect
        self.models: Dict[str, SchemaModel] = {}

    def analyze_file(self, file_path: str, content: str):
        """Analyze a file and extract data models."""
        ext = Path(file_path).suffix.lower()

        if ext in ('.ts', '.tsx'):
            self._extract_typescript_models(file_path, content)
        elif ext == '.py':
            self._extract_python_models(file_path, content)

    def _extract_typescript_models(self, file_path: str, content: str):
        """Extract models from TypeScript interfaces."""
        # Match interfaces that look like data models
        interface_pattern = r'interface\s+(\w+)(?:\s+extends\s+(\w+))?\s*\{([^}]+)\}'

        for match in re.finditer(interface_pattern, content, re.MULTILINE | re.DOTALL):
            name = match.group(1)
            extends = match.group(2)
            fields_str = match.group(3)

            # Check if this looks like a data model
            is_model = (
                any(kw in name for kw in ['Model', 'Entity', 'Schema', 'Data', 'DTO', 'Record']) or
                'id' in fields_str.lower() or
                'created' in fields_str.lower() or
                'updated' in fields_str.lower()
            )

            if not is_model:
                continue

            fields = self._parse_ts_fields(fields_str)

            if fields:
                model = SchemaModel(
                    name=self._to_table_name(name),
                    fields=fields,
                    source_file=file_path
                )

                # Handle extends
                if extends and extends in self.models:
                    # Add parent fields
                    parent_fields = self.models[extends].fields
                    model.fields = parent_fields + [f for f in fields if f.name not in [pf.name for pf in parent_fields]]

                self.models[name] = model

        # Also check for type definitions
        type_pattern = r'type\s+(\w+)\s*=\s*\{([^}]+)\}'
        for match in re.finditer(type_pattern, content, re.MULTILINE | re.DOTALL):
            name = match.group(1)
            fields_str = match.group(2)

            if any(kw in name for kw in ['Model', 'Entity', 'Schema', 'Data']):
                fields = self._parse_ts_fields(fields_str)
                if fields:
                    self.models[name] = SchemaModel(
                        name=self._to_table_name(name),
                        fields=fields,
                        source_file=file_path
                    )

    def _parse_ts_fields(self, fields_str: str) -> List[SchemaField]:
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

                # Handle array types
                is_array = type_hint.endswith('[]') or type_hint.startswith('Array<')

                # Clean up type
                clean_type = type_hint.replace('[]', '').replace('Array<', '').replace('>', '').strip()

                # Detect if it's a relation
                is_relation = clean_type[0].isupper() and clean_type not in self.TS_TO_SQL

                field = SchemaField(
                    name=name,
                    type=clean_type,
                    nullable=optional,
                    primary_key=name.lower() == 'id',
                    foreign_key=clean_type if is_relation else None
                )

                fields.append(field)

        return fields[:30]  # Limit fields

    def _extract_python_models(self, file_path: str, content: str):
        """Extract models from Python classes."""
        # Check for SQLAlchemy models
        if 'Column' in content or 'declarative_base' in content:
            self._extract_sqlalchemy_models(file_path, content)
        # Check for Pydantic models
        elif 'BaseModel' in content:
            self._extract_pydantic_models(file_path, content)
        # Check for dataclasses
        elif '@dataclass' in content:
            self._extract_dataclass_models(file_path, content)

    def _extract_sqlalchemy_models(self, file_path: str, content: str):
        """Extract SQLAlchemy ORM models."""
        class_pattern = r'class\s+(\w+)\(.*Base.*\):\s*\n((?:[ \t]+.*\n)*)'

        for match in re.finditer(class_pattern, content):
            name = match.group(1)
            body = match.group(2)

            fields = []
            column_pattern = r'(\w+)\s*=\s*Column\(([^)]+)\)'

            for col_match in re.finditer(column_pattern, body):
                col_name = col_match.group(1)
                col_def = col_match.group(2)

                # Parse column type
                type_match = re.search(r'(\w+)(?:\([^)]*\))?', col_def)
                col_type = type_match.group(1) if type_match else 'String'

                fields.append(SchemaField(
                    name=col_name,
                    type=col_type,
                    nullable='nullable=True' in col_def,
                    primary_key='primary_key=True' in col_def,
                    unique='unique=True' in col_def
                ))

            if fields:
                self.models[name] = SchemaModel(
                    name=self._to_table_name(name),
                    fields=fields,
                    source_file=file_path
                )

    def _extract_pydantic_models(self, file_path: str, content: str):
        """Extract Pydantic models."""
        class_pattern = r'class\s+(\w+)\(.*BaseModel.*\):\s*\n((?:[ \t]+.*\n)*)'

        for match in re.finditer(class_pattern, content):
            name = match.group(1)
            body = match.group(2)

            fields = []
            field_pattern = r'(\w+):\s+(?:Optional\[)?(\w+)(?:\])?(?:\s*=\s*[^#\n]+)?'

            for field_match in re.finditer(field_pattern, body):
                field_name = field_match.group(1)
                field_type = field_match.group(2)
                is_optional = 'Optional' in field_match.group(0)

                fields.append(SchemaField(
                    name=field_name,
                    type=field_type,
                    nullable=is_optional,
                    primary_key=field_name.lower() == 'id'
                ))

            if fields:
                self.models[name] = SchemaModel(
                    name=self._to_table_name(name),
                    fields=fields,
                    source_file=file_path
                )

    def _extract_dataclass_models(self, file_path: str, content: str):
        """Extract dataclass models."""
        class_pattern = r'@dataclass[^\n]*\nclass\s+(\w+):\s*\n((?:[ \t]+.*\n)*)'

        for match in re.finditer(class_pattern, content):
            name = match.group(1)
            body = match.group(2)

            fields = []
            field_pattern = r'(\w+):\s+(?:Optional\[)?(\w+)(?:\])?'

            for field_match in re.finditer(field_pattern, body):
                fields.append(SchemaField(
                    name=field_match.group(1),
                    type=field_match.group(2),
                    nullable='Optional' in field_match.group(0)
                ))

            if fields:
                self.models[name] = SchemaModel(
                    name=self._to_table_name(name),
                    fields=fields,
                    source_file=file_path
                )

    def _to_table_name(self, name: str) -> str:
        """Convert model name to table name (camelCase to snake_case)."""
        # Remove common suffixes
        name = re.sub(r'(Model|Entity|Schema|DTO|Data)$', '', name)
        # Convert to snake_case
        return re.sub(r'([a-z])([A-Z])', r'\1_\2', name).lower() + 's'

    def analyze_project(self, project_path: str) -> Dict[str, SchemaModel]:
        """Analyze an entire project."""
        project = Path(project_path)
        skip_dirs = {'node_modules', 'venv', '__pycache__', '.git', 'dist', 'build', '.next'}

        for root, dirs, files in os.walk(project):
            dirs[:] = [d for d in dirs if d not in skip_dirs]

            for file in files:
                ext = Path(file).suffix.lower()
                if ext in ('.ts', '.tsx', '.py'):
                    file_path = Path(root) / file
                    try:
                        content = file_path.read_text(encoding='utf-8', errors='ignore')
                        rel_path = str(file_path.relative_to(project))
                        self.analyze_file(rel_path, content)
                    except Exception as e:
                        print(f"Warning: Could not analyze {file_path}: {e}")

        return self.models

    def to_sql(self) -> str:
        """Generate SQL CREATE TABLE statements."""
        lines = []

        for model in self.models.values():
            lines.append(f"-- Table: {model.name}")
            lines.append(f"-- Source: {model.source_file}")
            lines.append(f"CREATE TABLE {model.name} (")

            field_defs = []
            for field in model.fields:
                # Skip relation fields
                if field.foreign_key:
                    continue

                # Map type
                sql_type = self.TS_TO_SQL.get(field.type, self.PYTHON_TO_SQL.get(field.type, 'VARCHAR(255)'))

                # Build field definition
                parts = [f"    {field.name}", sql_type]

                if field.primary_key:
                    parts.append("PRIMARY KEY")
                    if self.dialect == 'postgresql':
                        parts[-1] = "SERIAL PRIMARY KEY" if sql_type == 'INTEGER' else "PRIMARY KEY"
                elif not field.nullable:
                    parts.append("NOT NULL")

                if field.unique and not field.primary_key:
                    parts.append("UNIQUE")

                if field.default:
                    parts.append(f"DEFAULT {field.default}")

                field_defs.append(' '.join(parts))

            # Add foreign keys
            for field in model.fields:
                if field.foreign_key:
                    ref_table = self._to_table_name(field.foreign_key)
                    field_defs.append(f"    FOREIGN KEY ({field.name}_id) REFERENCES {ref_table}(id)")

            # Add timestamps if not present
            field_names = [f.name for f in model.fields]
            if 'created_at' not in field_names:
                field_defs.append("    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            if 'updated_at' not in field_names:
                field_defs.append("    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

            lines.append(',\n'.join(field_defs))
            lines.append(");\n")

        return '\n'.join(lines)

    def to_prisma(self) -> str:
        """Generate Prisma schema."""
        lines = [
            "// Prisma Schema",
            "// Generated from code analysis",
            "",
            'generator client {',
            '  provider = "prisma-client-js"',
            '}',
            "",
            f'datasource db {{',
            f'  provider = "{self._get_prisma_provider()}"',
            f'  url      = env("DATABASE_URL")',
            f'}}',
            ""
        ]

        for model in self.models.values():
            lines.append(f"// Source: {model.source_file}")
            lines.append(f"model {model.name.capitalize().rstrip('s')} {{")

            # Add id if not present
            field_names = [f.name.lower() for f in model.fields]
            if 'id' not in field_names:
                lines.append("  id        Int      @id @default(autoincrement())")

            for field in model.fields:
                if field.foreign_key:
                    # Add relation field
                    prisma_type = self.TS_TO_PRISMA.get('number', 'Int')
                    lines.append(f"  {field.name}Id  Int")
                    lines.append(f"  {field.name}   {field.foreign_key} @relation(fields: [{field.name}Id], references: [id])")
                else:
                    prisma_type = self.TS_TO_PRISMA.get(field.type, self.PYTHON_TO_PRISMA.get(field.type, 'String'))

                    attrs = []
                    if field.primary_key:
                        attrs.append("@id")
                        if prisma_type == 'Int':
                            attrs.append("@default(autoincrement())")
                    elif not field.nullable:
                        pass  # Required by default in Prisma
                    else:
                        attrs.append("?")

                    if field.unique and not field.primary_key:
                        attrs.append("@unique")

                    attr_str = ' '.join(attrs)
                    lines.append(f"  {field.name}  {prisma_type}{attr_str}")

            # Add timestamps
            if 'created_at' not in field_names:
                lines.append("  createdAt  DateTime @default(now()) @map(\"created_at\")")
            if 'updated_at' not in field_names:
                lines.append("  updatedAt  DateTime @updatedAt @map(\"updated_at\")")

            lines.append(f"}}")
            lines.append("")

        return '\n'.join(lines)

    def _get_prisma_provider(self) -> str:
        """Get Prisma provider from dialect."""
        providers = {
            'postgresql': 'postgresql',
            'mysql': 'mysql',
            'sqlite': 'sqlite',
            'sqlserver': 'sqlserver',
        }
        return providers.get(self.dialect, 'postgresql')


import os


def main():
    parser = argparse.ArgumentParser(description='Generate database schemas from code')
    parser.add_argument('project_path', help='Path to project directory')
    parser.add_argument('--format', choices=['sql', 'prisma'], default='sql', help='Output format')
    parser.add_argument('--dialect', choices=['postgresql', 'mysql', 'sqlite'], default='postgresql', help='SQL dialect')
    parser.add_argument('--output', '-o', help='Output file path')
    args = parser.parse_args()

    generator = SchemaGenerator(dialect=args.dialect)
    generator.analyze_project(args.project_path)

    if args.format == 'sql':
        output = generator.to_sql()
    else:
        output = generator.to_prisma()

    if args.output:
        Path(args.output).write_text(output, encoding='utf-8')
        print(f"Schema saved to: {args.output}")
    else:
        print(output)

    print(f"\nGenerated schemas for {len(generator.models)} models")


if __name__ == '__main__':
    main()
