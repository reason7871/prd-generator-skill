---
name: prd-generator
description: Generate comprehensive PRD (Product Requirements Document) from local codebase or GitHub repository. Includes deep code analysis, API extraction, data model inference, page screenshots, and supports both .md and .docx output. Use when user asks to "generate PRD", "create product doc", "analyze codebase for documentation", or provides a GitHub repo/local project path. **IMPORTANT**: Always start with interactive questions to understand user needs before generating.
compatibility: Requires Playwright for screenshots (optional), python-docx for Word output
---

# PRD Generator

Generate comprehensive Product Requirements Documents from code analysis with interactive guidance.

## When to Use

Invoke this skill when the user wants to:
- Generate a PRD from a local project
- Generate a PRD from a GitHub repository (public or private)
- Create product documentation with deep code analysis
- Get analysis of a codebase with screenshots

## Workflow

### Step 0: Interactive Requirements Gathering (REQUIRED)

**Before starting analysis, ask the user these questions:**

```
1. 📋 PRD Focus Areas
   Which sections are most important for this PRD?
   - [ ] Technical Architecture (system design, APIs, data models)
   - [ ] User Features (UI/UX, user flows, interactions)
   - [ ] Business Requirements (objectives, metrics, roadmap)
   - [ ] All sections equally (default)

2. 🎯 Target Audience
   Who will read this PRD?
   - Developers/Technical team
   - Product managers/ stakeholders
   - Investors/Executives
   - Mixed audience (default)

3. 📊 Detail Level
   How detailed should the analysis be?
   - Quick overview (key features only)
   - Standard (default - balanced coverage)
   - Deep dive (exhaustive code analysis with examples)

4. 🖼️ Screenshots
   Is the application running/accessible for screenshots?
   - Yes, URL: [provide URL]
   - No, skip screenshots
   - Local app, will start it first

5. 📄 Output Format
   - Markdown (.md) - default
   - Word (.docx)
   - Both formats

6. 🌐 Language
   - Same as conversation (default)
   - English
   - Chinese (中文)
```

**Use AskUserQuestion tool to gather these preferences efficiently.**

### Step 1: Acquire Codebase

**For local projects:**
- Use Glob and Read tools to explore the project structure
- Identify the tech stack from `package.json`, `requirements.txt`, `go.mod`, etc.

**For GitHub repositories (PRIORITY: Use zread MCP):**

**Method 1: zread MCP Tools (Preferred for public repos)**

Use zread MCP tools to read GitHub repos directly without cloning:

1. **Get repository structure:**
```
mcp__zread__get_repo_structure
- repo_name: "owner/repo"
- dir_path: "/" (optional, for subdirectories)
```

2. **Read file contents:**
```
mcp__zread__read_file
- repo_name: "owner/repo"
- file_path: "src/index.ts"
```

3. **Search documentation/issues/commits:**
```
mcp__zread__search_doc
- repo_name: "owner/repo"
- query: "API endpoints"
- language: "en" or "zh"
```

**Method 2: Git Clone (Fallback or for private repos)**

```bash
git clone --depth 1 https://github.com/owner/repo.git /tmp/prd-analysis/repo
```

### Step 2: Deep Code Analysis

Run the enhanced analysis script:

```bash
python <skill-path>/scripts/analyze_codebase.py <project-path> --deep
```

**Analysis includes:**

#### 2.1 Project Type Detection
- Frontend: React/Vue/Angular/Svelte/Vanilla
- Backend: Node.js/Python/Go/Java/Ruby/PHP
- Full-stack: Next.js/Nuxt/SvelteKit/Django/Flask/FastAPI
- Mobile: React Native/Flutter/Swift/Kotlin

#### 2.2 API Endpoint Extraction
Automatically extract REST/GraphQL endpoints:
- HTTP methods (GET, POST, PUT, DELETE)
- Route paths and parameters
- Request/Response schemas
- Authentication requirements

#### 2.3 Data Model Inference
Identify data structures from:
- TypeScript interfaces/types
- Python dataclasses/Pydantic models
- Database schemas (Prisma, SQLAlchemy, etc.)
- GraphQL schemas

#### 2.4 Component Analysis
For frontend projects:
- Component hierarchy
- Props and state management
- Key user interactions
- Styling approach

#### 2.5 Dependency Graph
Generate dependency relationships:
- Internal module dependencies
- External package dependencies
- Service connections

### Step 3: Capture Screenshots (if applicable)

If the user provides a running app URL:

```bash
python <skill-path>/scripts/capture_screenshots.py --url <app-url> --output <output-dir> --routes <route-list>
```

The script uses Playwright to:
1. Discover all pages/routes automatically (optional)
2. Capture full-page screenshots
3. Capture mobile and desktop viewports
4. Name them based on route/path

### Step 4: Generate PRD Document

Use the enhanced template from `references/prd_template.md`.

**PRD Structure (Enhanced):**

```markdown
# [Project Name] - Product Requirements Document

## 1. Executive Summary
- Project overview
- Core value proposition
- Target users

## 2. Product Overview
- Product background
- Business objectives
- Success metrics

## 3. User Personas
- Primary users
- User journeys

## 4. Functional Requirements
### 4.1 Frontend Features
### 4.2 Backend Features
### 4.3 API Endpoints (NEW)

## 5. Technical Architecture
### 5.1 Tech Stack
### 5.2 System Architecture
### 5.3 API Documentation
### 5.4 Data Models (ENHANCED)
### 5.5 Dependency Graph (NEW)

## 6. Data Models (DETAILED)
- Entity relationships
- Schema definitions
- Code examples

## 7. Non-Functional Requirements
- Performance requirements
- Security considerations
- Scalability

## 8. UI/UX Documentation
- Page screenshots
- Component library
- Design patterns

## 9. Testing Strategy (NEW)
- Unit tests
- Integration tests
- E2E tests

## 10. Deployment Guide (NEW)
- Environment setup
- Build process
- Deployment steps

## 11. Future Roadmap
- Planned features
- Technical debt
- Improvement suggestions

## 12. Appendix
- Glossary
- References
- Change log
```

### Step 5: Output Generation

**For Markdown (.md):**
Write directly to the specified output path.

**For Word (.docx):**
Use the conversion script:
```bash
python <skill-path>/scripts/convert_to_docx.py <input.md> <output.docx>
```

Features:
- Proper heading styles
- Code block formatting
- Table support
- Image embedding (for screenshots)
- Table of contents

**For Both:**
Generate both formats sequentially.

## Analysis Depth Guidelines

Based on user's selected detail level:

| Level | Code Lines Read | API Analysis | Component Analysis | Code Examples |
|-------|-----------------|--------------|-------------------|---------------|
| Quick | Top 20 files | Endpoints only | Names only | None |
| Standard | All source files | Endpoints + params | Props/State | Key snippets |
| Deep | All files + tests | Full API docs | Full component tree | Detailed examples |

## Screenshot Handling

Screenshots enhance the PRD significantly. Options:

1. **Live app provided**: Use Playwright to capture automatically
2. **Can start locally**: Ask user if they want to start the app first
3. **No app available**: Include placeholder sections noting where screenshots should go

**Screenshot Configuration:**
```python
# In capture_screenshots.py
VIEWPORTS = {
    'desktop': {'width': 1920, 'height': 1080},
    'tablet': {'width': 768, 'height': 1024},
    'mobile': {'width': 375, 'height': 812}
}
```

## GitHub Token Security

When handling private repos:
- Never log or display the token
- Use environment variables when possible: `GITHUB_TOKEN`
- Clean up cloned repos after analysis
- Warn user if token has been shared in chat

## Example Usage

**Interactive session:**
```
User: Generate a PRD for my project at ~/projects/my-app

Assistant: [Uses AskUserQuestion to gather preferences]
- Focus: Technical Architecture
- Audience: Developers
- Detail: Deep dive
- Screenshots: Yes, at localhost:3000
- Format: Both .md and .docx

[Proceeds with analysis and generation]
```

**Quick generation:**
```
User: Create a quick PRD for https://github.com/owner/repo

Assistant: [Uses default settings, skips interactive questions]
[Generates standard PRD.md]
```

## Error Handling

- **Repo not found**: Verify URL and access permissions
- **Invalid token**: Guide user to create a GitHub Personal Access Token
- **App not running**: Skip screenshots, note in PRD
- **Large codebase**: Focus on main modules, offer to exclude certain directories
- **Unsupported language**: Do best-effort analysis, note limitations
- **Playwright not installed**: Guide user: `pip install playwright && playwright install`

## Output Location

Default output: `<project-directory>/PRD.md` or `<project-directory>/PRD.docx`

User can specify custom output path.

## Advanced Features

### ER Diagram Generation

Generate database entity-relationship diagrams from code:

```bash
python <skill-path>/scripts/generate_er_diagram.py <project-path> --format mermaid
python <skill-path>/scripts/generate_er_diagram.py <project-path> --format dbml
```

**Supported Sources:**
- TypeScript interfaces
- Python dataclasses/Pydantic models
- SQL CREATE TABLE statements
- Prisma schema files

**Output Formats:**
- Mermaid diagram (for Markdown)
- DBML (for dbdiagram.io)

### API Collection Export

Generate importable API collections:

```bash
python <skill-path>/scripts/export_api_collection.py <project-path> --format postman
python <skill-path>/scripts/export_api_collection.py <project-path> --format insomnia
python <skill-path>/scripts/export_api_collection.py <project-path> --format openapi
```

**Supported Frameworks:**
- Next.js API Routes
- Express.js
- FastAPI
- Flask

### User Flow Diagrams

Generate user flow diagrams:

```bash
python <skill-path>/scripts/generate_user_flow.py <project-path> --format mermaid
python <skill-path>/scripts/generate_user_flow.py <project-path> --format plantuml
```

**Detects:**
- Page routes and navigation
- Form submissions
- API calls
- Conditional rendering

### TODO/FIXME Analysis

Analyze code comments for issues:

```bash
python <skill-path>/scripts/analyze_todos.py <project-path> --format markdown
```

**Detects:**
- TODO comments with priorities
- FIXME items
- Security vulnerabilities (eval, XSS, hardcoded secrets)
- Performance issues
- Code smells

### Database Schema Generation

Generate database schemas from models:

```bash
python <skill-path>/scripts/generate_schema.py <project-path> --format sql --dialect postgresql
python <skill-path>/scripts/generate_schema.py <project-path> --format prisma
```

**Supported:**
- TypeScript interfaces → SQL/Prisma
- Python dataclasses → SQL/Prisma
- SQLAlchemy models → Prisma

## Skill Files

```
prd-generator/
├── SKILL.md                    # This file
├── scripts/
│   ├── analyze_codebase.py     # Deep code analysis
│   ├── capture_screenshots.py  # Playwright screenshots
│   ├── convert_to_docx.py      # Markdown to Word conversion
│   ├── generate_er_diagram.py  # ER diagram generation
│   ├── export_api_collection.py # Postman/Insomnia/OpenAPI export
│   ├── generate_user_flow.py   # User flow diagrams
│   ├── analyze_todos.py        # TODO/FIXME analysis
│   └── generate_schema.py      # Database schema generation
└── references/
    └── prd_template.md         # Enhanced PRD template
```

## Dependencies

**Required:**
- Python 3.8+

**Optional:**
- `playwright` - For screenshots
- `python-docx` - For Word output
- `Pillow` - For image processing

Install all:
```bash
pip install playwright python-docx Pillow
playwright install chromium
```
