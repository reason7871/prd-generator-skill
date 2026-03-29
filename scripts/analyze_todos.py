#!/usr/bin/env python3
"""
Analyze TODO/FIXME comments and generate improvement suggestions.
Detects code quality issues and generates actionable recommendations.
"""

import re
import argparse
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum


class IssueType(Enum):
    TODO = "todo"
    FIXME = "fixme"
    HACK = "hack"
    XXX = "xxx"
    BUG = "bug"
    SECURITY = "security"
    PERFORMANCE = "performance"
    CODE_SMELL = "code_smell"


class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class CodeIssue:
    """Represents a code issue or TODO."""
    type: IssueType
    severity: Severity
    message: str
    file: str
    line: int
    context: str
    suggestion: str = ""


@dataclass
class AnalysisReport:
    """Complete analysis report."""
    issues: List[CodeIssue] = field(default_factory=list)
    statistics: Dict = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)


class CodeAnalyzer:
    """Analyze code for issues and improvement opportunities."""

    # TODO/FIXME patterns
    TODO_PATTERNS = {
        IssueType.TODO: [
            r'(?:^|\s)//\s*TODO(?:\s*:|\s+\[([^\]]+)\])?:?\s*(.+)$',
            r'(?:^|\s)#\s*TODO(?:\s*:|\s+\[([^\]]+)\])?:?\s*(.+)$',
            r'/\*\s*TODO(?:\s*:|\s+\[([^\]]+)\])?:?\s*(.+?)\s*\*/',
        ],
        IssueType.FIXME: [
            r'(?:^|\s)//\s*FIXME(?:\s*:|\s+\[([^\]]+)\])?:?\s*(.+)$',
            r'(?:^|\s)#\s*FIXME(?:\s*:|\s+\[([^\]]+)\])?:?\s*(.+)$',
            r'/\*\s*FIXME(?:\s*:|\s+\[([^\]]+)\])?:?\s*(.+?)\s*\*/',
        ],
        IssueType.HACK: [
            r'(?:^|\s)//\s*HACK(?:\s*:|\s+\[([^\]]+)\])?:?\s*(.+)$',
            r'(?:^|\s)#\s*HACK(?:\s*:|\s+\[([^\]]+)\])?:?\s*(.+)$',
        ],
        IssueType.XXX: [
            r'(?:^|\s)//\s*XXX(?:\s*:|\s+\[([^\]]+)\])?:?\s*(.+)$',
            r'(?:^|\s)#\s*XXX(?:\s*:|\s+\[([^\]]+)\])?:?\s*(.+)$',
        ],
    }

    # Security patterns
    SECURITY_PATTERNS = [
        (r'eval\s*\(', 'Use of eval() is dangerous', Severity.HIGH),
        (r'innerHTML\s*=', 'Direct innerHTML assignment may cause XSS', Severity.MEDIUM),
        (r'dangerouslySetInnerHTML', 'React dangerouslySetInnerHTML may cause XSS', Severity.MEDIUM),
        (r'password\s*=\s*[\'"][^\'"]+[\'"]', 'Hardcoded password detected', Severity.CRITICAL),
        (r'api[_-]?key\s*=\s*[\'"][^\'"]+[\'"]', 'Hardcoded API key detected', Severity.CRITICAL),
        (r'secret\s*=\s*[\'"][^\'"]+[\'"]', 'Hardcoded secret detected', Severity.CRITICAL),
        (r'SELECT\s+\*\s+FROM', 'SELECT * may expose sensitive data', Severity.LOW),
        (r'exec\s*\([^)]*\+', 'Potential SQL injection', Severity.HIGH),
        (r'__dirname\s*\+\s*[\'"]', 'Potential path traversal', Severity.MEDIUM),
    ]

    # Performance patterns
    PERFORMANCE_PATTERNS = [
        (r'\.forEach\([^)]*\)\s*{\s*(?:await|async)', 'await inside forEach - use for...of instead', Severity.MEDIUM),
        (r'JSON\.parse\(JSON\.stringify\(', 'Inefficient deep copy', Severity.LOW),
        (r'new\s+RegExp\([^)]*\+\s*', 'RegExp created in loop', Severity.MEDIUM),
        (r'document\.querySelector\s*\([^)]*\)\s*inside\s*(?:for|while)', 'DOM query in loop', Severity.HIGH),
        (r'\.map\([^)]*\)\.filter\(', 'Chain map/filter can be optimized', Severity.LOW),
    ]

    # Code smell patterns
    CODE_SMELL_PATTERNS = [
        (r'function\s+\w+\s*\([^)]{100,}\)', 'Function with too many parameters', Severity.LOW),
        (r'if\s*\([^)]{200,}\)', 'Complex condition', Severity.LOW),
        (r'console\.log\(', 'Console.log should be removed in production', Severity.LOW),
        (r'debugger;', 'Debugger statement should be removed', Severity.MEDIUM),
        (r'any\s*[\):]', 'Use of any type defeats TypeScript benefits', Severity.LOW),
        (r'@ts-ignore', 'TypeScript ignore comment', Severity.LOW),
        (r'eslint-disable', 'ESLint disabled', Severity.LOW),
    ]

    def __init__(self):
        self.report = AnalysisReport()

    def analyze_file(self, file_path: str, content: str):
        """Analyze a single file for issues."""
        lines = content.split('\n')

        # Check TODO/FIXME comments
        self._check_todos(file_path, content, lines)

        # Check security issues
        self._check_security(file_path, content, lines)

        # Check performance issues
        self._check_performance(file_path, content, lines)

        # Check code smells
        self._check_code_smells(file_path, content, lines)

    def _check_todos(self, file_path: str, content: str, lines: List[str]):
        """Check for TODO/FIXME comments."""
        for issue_type, patterns in self.TODO_PATTERNS.items():
            for pattern in patterns:
                for match in re.finditer(pattern, content, re.MULTILINE | re.IGNORECASE):
                    priority = match.group(1) if match.group(1) else None
                    message = match.group(2).strip() if match.lastindex >= 2 else ""

                    line_num = content[:match.start()].count('\n') + 1
                    context = lines[line_num - 1].strip() if line_num <= len(lines) else ""

                    severity = self._determine_severity(priority, issue_type)

                    issue = CodeIssue(
                        type=issue_type,
                        severity=severity,
                        message=message or f"{issue_type.value.upper()} comment",
                        file=file_path,
                        line=line_num,
                        context=context[:100],
                        suggestion=self._generate_suggestion(issue_type, message)
                    )
                    self.report.issues.append(issue)

    def _check_security(self, file_path: str, content: str, lines: List[str]):
        """Check for security vulnerabilities."""
        for pattern, message, severity in self.SECURITY_PATTERNS:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[:match.start()].count('\n') + 1
                context = lines[line_num - 1].strip() if line_num <= len(lines) else ""

                issue = CodeIssue(
                    type=IssueType.SECURITY,
                    severity=severity,
                    message=message,
                    file=file_path,
                    line=line_num,
                    context=context[:100],
                    suggestion="Review and fix this security issue before deployment."
                )
                self.report.issues.append(issue)

    def _check_performance(self, file_path: str, content: str, lines: List[str]):
        """Check for performance issues."""
        for pattern, message, severity in self.PERFORMANCE_PATTERNS:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[:match.start()].count('\n') + 1
                context = lines[line_num - 1].strip() if line_num <= len(lines) else ""

                issue = CodeIssue(
                    type=IssueType.PERFORMANCE,
                    severity=severity,
                    message=message,
                    file=file_path,
                    line=line_num,
                    context=context[:100],
                    suggestion="Consider optimizing this code for better performance."
                )
                self.report.issues.append(issue)

    def _check_code_smells(self, file_path: str, content: str, lines: List[str]):
        """Check for code smells."""
        for pattern, message, severity in self.CODE_SMELL_PATTERNS:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[:match.start()].count('\n') + 1
                context = lines[line_num - 1].strip() if line_num <= len(lines) else ""

                issue = CodeIssue(
                    type=IssueType.CODE_SMELL,
                    severity=severity,
                    message=message,
                    file=file_path,
                    line=line_num,
                    context=context[:100],
                    suggestion="Consider refactoring this code."
                )
                self.report.issues.append(issue)

    def _determine_severity(self, priority: Optional[str], issue_type: IssueType) -> Severity:
        """Determine issue severity from priority tag or type."""
        if priority:
            priority_lower = priority.lower()
            if priority_lower in ('high', 'critical', 'urgent', 'important'):
                return Severity.HIGH
            elif priority_lower in ('medium', 'normal'):
                return Severity.MEDIUM
            elif priority_lower in ('low', 'minor', 'nice-to-have'):
                return Severity.LOW

        # Default severity by type
        type_severity = {
            IssueType.BUG: Severity.HIGH,
            IssueType.SECURITY: Severity.HIGH,
            IssueType.FIXME: Severity.MEDIUM,
            IssueType.HACK: Severity.MEDIUM,
            IssueType.XXX: Severity.MEDIUM,
            IssueType.TODO: Severity.LOW,
            IssueType.PERFORMANCE: Severity.LOW,
            IssueType.CODE_SMELL: Severity.LOW,
        }
        return type_severity.get(issue_type, Severity.LOW)

    def _generate_suggestion(self, issue_type: IssueType, message: str) -> str:
        """Generate a suggestion based on issue type."""
        suggestions = {
            IssueType.TODO: "Create a ticket or issue to track this task.",
            IssueType.FIXME: "This needs to be fixed before production deployment.",
            IssueType.HACK: "Consider a more robust solution that doesn't require a workaround.",
            IssueType.XXX: "Review this code for potential issues.",
            IssueType.BUG: "Investigate and fix this known bug.",
            IssueType.SECURITY: "Review and fix this security issue before deployment.",
            IssueType.PERFORMANCE: "Profile and optimize this code if it's in a hot path.",
            IssueType.CODE_SMELL: "Consider refactoring for better maintainability.",
        }
        return suggestions.get(issue_type, "Review and address this issue.")

    def analyze_project(self, project_path: str) -> AnalysisReport:
        """Analyze an entire project."""
        project = Path(project_path)
        skip_dirs = {'node_modules', 'venv', '__pycache__', '.git', 'dist', 'build', '.next', 'coverage', '.idea', '.vscode'}
        skip_files = {'.min.js', '.min.css', 'package-lock.json', 'yarn.lock'}

        for root, dirs, files in os.walk(project):
            dirs[:] = [d for d in dirs if d not in skip_dirs]

            for file in files:
                # Skip minified and lock files
                if any(skip in file for skip in skip_files):
                    continue

                ext = Path(file).suffix.lower()
                if ext in ('.ts', '.tsx', '.js', '.jsx', '.py', '.go', '.java', '.rb', '.php'):
                    file_path = Path(root) / file
                    try:
                        content = file_path.read_text(encoding='utf-8', errors='ignore')
                        rel_path = str(file_path.relative_to(project))
                        self.analyze_file(rel_path, content)
                    except Exception as e:
                        print(f"Warning: Could not analyze {file_path}: {e}")

        # Calculate statistics
        self._calculate_statistics()

        # Generate recommendations
        self._generate_recommendations()

        return self.report

    def _calculate_statistics(self):
        """Calculate analysis statistics."""
        self.report.statistics = {
            'total_issues': len(self.report.issues),
            'by_type': defaultdict(int),
            'by_severity': defaultdict(int),
            'by_file': defaultdict(int),
        }

        for issue in self.report.issues:
            self.report.statistics['by_type'][issue.type.value] += 1
            self.report.statistics['by_severity'][issue.severity.value] += 1
            self.report.statistics['by_file'][issue.file] += 1

        # Convert defaultdicts to regular dicts
        self.report.statistics['by_type'] = dict(self.report.statistics['by_type'])
        self.report.statistics['by_severity'] = dict(self.report.statistics['by_severity'])
        self.report.statistics['by_file'] = dict(self.report.statistics['by_file'])

    def _generate_recommendations(self):
        """Generate overall recommendations."""
        recommendations = []

        # Check for critical issues
        critical = [i for i in self.report.issues if i.severity == Severity.CRITICAL]
        if critical:
            recommendations.append(f"🚨 **Critical**: {len(critical)} critical issues require immediate attention")

        # Check for security issues
        security = [i for i in self.report.issues if i.type == IssueType.SECURITY]
        if security:
            recommendations.append(f"🔒 **Security**: {len(security)} potential security vulnerabilities detected")

        # Check for TODOs without timeline
        todos = [i for i in self.report.issues if i.type == IssueType.TODO]
        if len(todos) > 10:
            recommendations.append(f"📝 **Tech Debt**: {len(todos)} TODOs accumulated - consider scheduling cleanup sprints")

        # Check for FIXMEs
        fixmes = [i for i in self.report.issues if i.type == IssueType.FIXME]
        if fixmes:
            recommendations.append(f"🔧 **Fix Required**: {len(fixmes)} FIXMEs need to be addressed")

        # Check for hacks
        hacks = [i for i in self.report.issues if i.type == IssueType.HACK]
        if hacks:
            recommendations.append(f"⚠️ **Workarounds**: {len(hacks)} hack implementations should be refactored")

        self.report.recommendations = recommendations

    def to_markdown(self) -> str:
        """Generate markdown report."""
        lines = ["# Code Analysis Report\n"]

        # Summary
        lines.append("## Summary\n")
        stats = self.report.statistics
        lines.append(f"- **Total Issues**: {stats['total_issues']}\n")

        if stats['by_severity']:
            lines.append("\n### By Severity\n")
            for severity, count in sorted(stats['by_severity'].items(), key=lambda x: ['critical', 'high', 'medium', 'low'].index(x[0])):
                emoji = {'critical': '🚨', 'high': '🔴', 'medium': '🟡', 'low': '🔵'}.get(severity, '⚪')
                lines.append(f"- {emoji} **{severity.title()}**: {count}\n")

        # Recommendations
        if self.report.recommendations:
            lines.append("\n## Recommendations\n")
            for rec in self.report.recommendations:
                lines.append(f"- {rec}\n")

        # Issues by type
        if stats['by_type']:
            lines.append("\n## Issues by Type\n")
            for issue_type, count in sorted(stats['by_type'].items()):
                lines.append(f"- **{issue_type.upper()}**: {count}\n")

        # Detailed issues
        if self.report.issues:
            lines.append("\n## Detailed Issues\n")

            # Group by severity
            for severity in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
                issues = [i for i in self.report.issues if i.severity == severity]
                if issues:
                    lines.append(f"\n### {severity.value.title()} Priority ({len(issues)})\n")
                    for issue in issues[:20]:  # Limit to 20 per category
                        lines.append(f"- **{issue.file}:{issue.line}** [{issue.type.value}]")
                        lines.append(f"  - {issue.message}")
                        if issue.suggestion:
                            lines.append(f"  - 💡 {issue.suggestion}")

        return ''.join(lines)

    def to_json(self) -> Dict:
        """Generate JSON report."""
        return {
            'statistics': self.report.statistics,
            'recommendations': self.report.recommendations,
            'issues': [
                {
                    'type': issue.type.value,
                    'severity': issue.severity.value,
                    'message': issue.message,
                    'file': issue.file,
                    'line': issue.line,
                    'context': issue.context,
                    'suggestion': issue.suggestion
                }
                for issue in self.report.issues
            ]
        }


import os


def main():
    parser = argparse.ArgumentParser(description='Analyze code for issues and TODOs')
    parser.add_argument('project_path', help='Path to project directory')
    parser.add_argument('--format', choices=['markdown', 'json'], default='markdown', help='Output format')
    parser.add_argument('--output', '-o', help='Output file path')
    parser.add_argument('--severity', choices=['critical', 'high', 'medium', 'low'], help='Filter by minimum severity')
    args = parser.parse_args()

    analyzer = CodeAnalyzer()
    report = analyzer.analyze_project(args.project_path)

    if args.severity:
        severity_order = ['critical', 'high', 'medium', 'low']
        min_index = severity_order.index(args.severity)
        report.issues = [i for i in report.issues if severity_order.index(i.severity.value) <= min_index]
        analyzer._calculate_statistics()

    if args.format == 'markdown':
        output = analyzer.to_markdown()
    else:
        output = json.dumps(analyzer.to_json(), indent=2)

    if args.output:
        Path(args.output).write_text(output, encoding='utf-8')
        print(f"Analysis saved to: {args.output}")
    else:
        print(output)

    print(f"\nFound {len(report.issues)} issues")


if __name__ == '__main__':
    main()
