#!/usr/bin/env python3
"""
Work Item Context Detection

Detects work item context from:
- Current git branch name
- Commit messages
- Environment variables
- Manual context setting

Supports common branch naming conventions:
- feature/AB#1234-description
- fix/AB#1234-short-desc
- bugfix/1234-description
- user/AB#1234/feature-name
- AB#1234
- 1234-description
"""

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from work_item_index import WorkItemIndexManager, WorkItem


class ContextSource(Enum):
    """Source of work item context detection."""
    BRANCH_NAME = "branch_name"
    COMMIT_MESSAGE = "commit_message"
    ENVIRONMENT = "environment"
    MANUAL = "manual"
    INDEX_MAPPING = "index_mapping"
    NONE = "none"


@dataclass
class WorkItemContext:
    """Current work item context."""
    work_item_id: Optional[int]
    work_item: Optional[WorkItem]
    source: ContextSource
    branch_name: Optional[str]
    confidence: float  # 0.0 to 1.0
    raw_match: Optional[str]  # The actual matched pattern
    suggested_area: Optional[str] = None  # Suggested ADO area path

    @property
    def has_context(self) -> bool:
        """Check if we have a valid work item context."""
        return self.work_item_id is not None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "work_item_id": self.work_item_id,
            "work_item": self.work_item.to_dict() if self.work_item else None,
            "source": self.source.value,
            "branch_name": self.branch_name,
            "confidence": self.confidence,
            "raw_match": self.raw_match,
            "suggested_area": self.suggested_area
        }


class BranchParser:
    """Parses branch names to extract work item IDs."""

    # Patterns ordered by specificity (most specific first)
    PATTERNS = [
        # Azure DevOps format: AB#1234
        (r'AB#(\d+)', 1.0),
        # Full ADO format with prefix
        (r'(?:feature|fix|bugfix|hotfix|release|user)/AB#(\d+)', 1.0),
        # Bare number with prefix
        (r'(?:feature|fix|bugfix|hotfix|release)/(\d+)(?:-|/|$)', 0.9),
        # User branch with work item
        (r'user/[^/]+/(?:AB#)?(\d+)', 0.9),
        # Number at start of branch (after prefix)
        (r'(?:feature|fix|bugfix|hotfix)/(\d{4,6})[-/]', 0.8),
        # Any AB# anywhere in branch
        (r'AB#(\d+)', 1.0),
        # Bare number that looks like work item (4-6 digits)
        (r'/(\d{4,6})[-/]', 0.6),
        # Number at very start
        (r'^(\d{4,6})[-/]', 0.5),
    ]

    @classmethod
    def parse(cls, branch_name: str) -> Tuple[Optional[int], float, Optional[str]]:
        """
        Parse a branch name to extract work item ID.

        Returns:
            Tuple of (work_item_id, confidence, raw_match)
        """
        if not branch_name:
            return None, 0.0, None

        for pattern, confidence in cls.PATTERNS:
            match = re.search(pattern, branch_name, re.IGNORECASE)
            if match:
                try:
                    work_item_id = int(match.group(1))
                    # Validate reasonable work item ID range
                    if 1 <= work_item_id <= 9999999:
                        return work_item_id, confidence, match.group(0)
                except (ValueError, IndexError):
                    continue

        return None, 0.0, None

    @classmethod
    def suggest_branch_name(cls, work_item_id: int, work_item: Optional[WorkItem] = None,
                           prefix: str = "feature") -> str:
        """
        Suggest a branch name for a work item.

        Args:
            work_item_id: The work item ID
            work_item: Optional WorkItem for title-based naming
            prefix: Branch prefix (feature, fix, bugfix, etc.)

        Returns:
            Suggested branch name
        """
        if work_item and work_item.title:
            # Slugify the title
            slug = re.sub(r'[^a-zA-Z0-9]+', '-', work_item.title.lower())
            slug = slug.strip('-')[:50]  # Limit length
            return f"{prefix}/AB#{work_item_id}-{slug}"
        return f"{prefix}/AB#{work_item_id}"


class CommitParser:
    """Parses commit messages to extract work item IDs."""

    # Patterns for commit messages
    PATTERNS = [
        # AB#1234 format (most common)
        (r'AB#(\d+)', 1.0),
        # Fixes #1234, Closes #1234, etc.
        (r'(?:fixes|closes|resolves|refs?|see)\s*#(\d+)', 0.8),
        # [1234] prefix format
        (r'\[(\d{4,6})\]', 0.7),
        # Work item: 1234
        (r'work\s*item[:\s]+(\d+)', 0.9),
        # Task: 1234
        (r'task[:\s]+(\d+)', 0.8),
        # Bug: 1234
        (r'bug[:\s]+(\d+)', 0.8),
    ]

    @classmethod
    def parse(cls, message: str) -> List[Tuple[int, float, str]]:
        """
        Parse a commit message to extract all work item references.

        Returns:
            List of (work_item_id, confidence, raw_match) tuples
        """
        results = []
        seen_ids = set()

        for pattern, confidence in cls.PATTERNS:
            for match in re.finditer(pattern, message, re.IGNORECASE):
                try:
                    work_item_id = int(match.group(1))
                    if 1 <= work_item_id <= 9999999 and work_item_id not in seen_ids:
                        results.append((work_item_id, confidence, match.group(0)))
                        seen_ids.add(work_item_id)
                except (ValueError, IndexError):
                    continue

        return results

    @classmethod
    def format_commit_reference(cls, work_item_id: int) -> str:
        """Format a work item reference for commit messages."""
        return f"AB#{work_item_id}"


class GitContext:
    """Git repository context detection."""

    @staticmethod
    def get_current_branch() -> Optional[str]:
        """Get the current git branch name."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                cwd=os.getcwd()
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
                return branch if branch != "HEAD" else None
            return None
        except Exception:
            return None

    @staticmethod
    def get_recent_commits(count: int = 10) -> List[str]:
        """Get recent commit messages."""
        try:
            result = subprocess.run(
                ["git", "log", f"-{count}", "--pretty=format:%s"],
                capture_output=True,
                text=True,
                cwd=os.getcwd()
            )
            if result.returncode == 0:
                return result.stdout.strip().split("\n")
            return []
        except Exception:
            return []

    @staticmethod
    def get_commit_sha() -> Optional[str]:
        """Get current commit SHA."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=os.getcwd()
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception:
            return None

    @staticmethod
    def is_git_repo() -> bool:
        """Check if current directory is in a git repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
                text=True,
                cwd=os.getcwd()
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def get_repo_root() -> Optional[str]:
        """Get the root directory of the git repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                cwd=os.getcwd()
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception:
            return None

    @staticmethod
    def get_changed_files() -> List[str]:
        """Get list of changed files in working directory."""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True,
                text=True,
                cwd=os.getcwd()
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split('\n')
            return []
        except Exception:
            return []


class AreaSuggester:
    """Suggests ADO area based on code context."""

    # Common source directories
    SOURCE_DIRS = {'src', 'lib', 'packages', 'apps', 'services', 'modules'}

    # Known category mappings (lowercase -> category)
    CATEGORY_MAPPINGS = {
        # Platform
        'auth': 'Platform', 'authentication': 'Platform', 'authorization': 'Platform',
        'identity': 'Platform', 'security': 'Platform', 'infrastructure': 'Platform',
        'common': 'Platform', 'shared': 'Platform', 'core': 'Platform',
        'logging': 'Platform', 'monitoring': 'Platform', 'telemetry': 'Platform',

        # Integrations
        'integration': 'Integrations', 'integrations': 'Integrations',
        'gateway': 'Integrations', 'connector': 'Integrations', 'connectors': 'Integrations',
        'external': 'Integrations', 'api': 'Integrations', 'apis': 'Integrations',

        # Clients
        'web': 'Clients', 'mobile': 'Clients', 'desktop': 'Clients',
        'cli': 'Clients', 'frontend': 'Clients', 'ui': 'Clients', 'client': 'Clients',

        # Operations
        'devops': 'Operations', 'deployment': 'Operations', 'deploy': 'Operations',
        'ops': 'Operations', 'operations': 'Operations',
    }

    def __init__(self, config_path: str = ".ado/config.json"):
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """Load ADO configuration."""
        try:
            return json.loads(Path(self.config_path).read_text())
        except Exception:
            return {}

    def suggest_from_cwd(self) -> Optional[str]:
        """Suggest area based on current working directory."""
        repo_root = GitContext.get_repo_root()
        if not repo_root:
            return None

        cwd = os.getcwd()
        try:
            rel_path = Path(cwd).relative_to(repo_root)
            return self._suggest_from_path(str(rel_path))
        except ValueError:
            return None

    def suggest_from_branch(self, branch_name: str) -> Optional[str]:
        """Suggest area based on branch name."""
        if not branch_name:
            return None

        # Extract component hint from branch
        # e.g., feature/orders/AB#1234-fix -> Orders
        # e.g., fix/auth-token-refresh -> Auth (-> Platform\Authentication)

        parts = branch_name.lower().replace('\\', '/').split('/')

        for part in parts:
            # Skip common prefixes
            if part in {'feature', 'fix', 'bugfix', 'hotfix', 'release', 'user'}:
                continue

            # Skip work item references
            if re.match(r'^(ab#)?\d+', part):
                continue

            # Try to extract component name
            # Remove trailing description after work item
            component = re.sub(r'-.*$', '', part)
            component = re.sub(r'^(ab#)?\d+[-_]?', '', component)

            if component and len(component) > 2:
                return self._suggest_area_for_component(component)

        return None

    def suggest_from_changed_files(self) -> Optional[str]:
        """Suggest area based on changed files."""
        changed_files = GitContext.get_changed_files()
        if not changed_files:
            return None

        # Find common path prefix
        if len(changed_files) == 1:
            return self._suggest_from_path(changed_files[0])

        # Find most common component directory
        components: Dict[str, int] = {}
        for file_path in changed_files:
            suggestion = self._suggest_from_path(file_path)
            if suggestion:
                components[suggestion] = components.get(suggestion, 0) + 1

        if components:
            # Return most common
            return max(components.keys(), key=lambda k: components[k])

        return None

    def _suggest_from_path(self, rel_path: str) -> Optional[str]:
        """Suggest area from a relative file path."""
        parts = Path(rel_path).parts

        # Skip source directory prefixes
        meaningful_parts = []
        skip_next = False

        for part in parts:
            if skip_next:
                skip_next = False
                continue

            part_lower = part.lower()

            # Skip common non-component directories
            if part_lower in self.SOURCE_DIRS:
                continue
            if part.startswith('.') or part.startswith('_'):
                continue
            if part_lower in {'test', 'tests', 'spec', 'specs', '__pycache__'}:
                continue

            meaningful_parts.append(part)

            # Usually first meaningful part is the component
            if len(meaningful_parts) >= 1:
                break

        if meaningful_parts:
            component = meaningful_parts[0]
            return self._suggest_area_for_component(component)

        return None

    def _suggest_area_for_component(self, component: str) -> str:
        """Generate area path for a component name."""
        project_name = self.config.get('project', '')
        component_lower = component.lower()

        # Clean up component name
        clean_name = re.sub(r'[-_]', '', component)
        clean_name = clean_name[0].upper() + clean_name[1:] if clean_name else component

        # Determine category
        category = self.CATEGORY_MAPPINGS.get(component_lower, 'Core')

        if project_name:
            return f"{project_name}\\{category}\\{clean_name}"
        return f"{category}\\{clean_name}"

    def suggest(self) -> Optional[str]:
        """
        Get best area suggestion using all available signals.

        Priority:
        1. Changed files (most specific)
        2. Current directory
        3. Branch name
        """
        # Try changed files first
        suggestion = self.suggest_from_changed_files()
        if suggestion:
            return suggestion

        # Try current directory
        suggestion = self.suggest_from_cwd()
        if suggestion:
            return suggestion

        # Try branch name
        branch = GitContext.get_current_branch()
        if branch:
            suggestion = self.suggest_from_branch(branch)
            if suggestion:
                return suggestion

        return None


class WorkItemContextDetector:
    """Detects work item context from various sources."""

    ENV_VAR_WORK_ITEM = "ADO_WORK_ITEM_ID"

    def __init__(self, index_manager: Optional[WorkItemIndexManager] = None,
                 config_path: str = ".ado/config.json"):
        """
        Initialize context detector.

        Args:
            index_manager: Optional WorkItemIndexManager for lookups
            config_path: Path to ADO config for area suggestions
        """
        self.index_manager = index_manager or WorkItemIndexManager()
        self.area_suggester = AreaSuggester(config_path)

    def detect(self, include_area_suggestion: bool = True) -> WorkItemContext:
        """
        Detect current work item context.

        Priority order:
        1. Environment variable
        2. Index mapping for current branch
        3. Branch name parsing
        4. Recent commit messages

        Args:
            include_area_suggestion: Whether to include area suggestion in context

        Returns:
            WorkItemContext with detected context
        """
        branch_name = GitContext.get_current_branch()

        # Get area suggestion if requested
        suggested_area = None
        if include_area_suggestion:
            suggested_area = self.area_suggester.suggest()

        # 1. Check environment variable
        env_id = os.environ.get(self.ENV_VAR_WORK_ITEM)
        if env_id:
            try:
                work_item_id = int(env_id)
                work_item = self.index_manager.get_work_item(work_item_id)
                # Use work item's area if available, otherwise use suggestion
                area = work_item.area_path if work_item and work_item.area_path else suggested_area
                return WorkItemContext(
                    work_item_id=work_item_id,
                    work_item=work_item,
                    source=ContextSource.ENVIRONMENT,
                    branch_name=branch_name,
                    confidence=1.0,
                    raw_match=env_id,
                    suggested_area=area
                )
            except ValueError:
                pass

        # 2. Check index mapping for current branch
        if branch_name:
            work_item = self.index_manager.get_work_item_for_branch(branch_name)
            if work_item:
                area = work_item.area_path if work_item.area_path else suggested_area
                return WorkItemContext(
                    work_item_id=work_item.id,
                    work_item=work_item,
                    source=ContextSource.INDEX_MAPPING,
                    branch_name=branch_name,
                    confidence=1.0,
                    raw_match=branch_name,
                    suggested_area=area
                )

        # 3. Parse branch name
        if branch_name:
            work_item_id, confidence, raw_match = BranchParser.parse(branch_name)
            if work_item_id:
                work_item = self.index_manager.get_work_item(work_item_id)
                area = work_item.area_path if work_item and work_item.area_path else suggested_area
                return WorkItemContext(
                    work_item_id=work_item_id,
                    work_item=work_item,
                    source=ContextSource.BRANCH_NAME,
                    branch_name=branch_name,
                    confidence=confidence,
                    raw_match=raw_match,
                    suggested_area=area
                )

        # 4. Check recent commits
        commits = GitContext.get_recent_commits(5)
        for commit in commits:
            refs = CommitParser.parse(commit)
            if refs:
                work_item_id, confidence, raw_match = refs[0]  # Take first match
                work_item = self.index_manager.get_work_item(work_item_id)
                area = work_item.area_path if work_item and work_item.area_path else suggested_area
                return WorkItemContext(
                    work_item_id=work_item_id,
                    work_item=work_item,
                    source=ContextSource.COMMIT_MESSAGE,
                    branch_name=branch_name,
                    confidence=confidence * 0.8,  # Reduce confidence for commit-based detection
                    raw_match=raw_match,
                    suggested_area=area
                )

        # No context found
        return WorkItemContext(
            work_item_id=None,
            work_item=None,
            source=ContextSource.NONE,
            branch_name=branch_name,
            confidence=0.0,
            raw_match=None,
            suggested_area=suggested_area
        )

    def set_context(self, work_item_id: int, link_to_branch: bool = True) -> WorkItemContext:
        """
        Manually set work item context.

        Args:
            work_item_id: Work item ID to set
            link_to_branch: If True, also link to current branch

        Returns:
            WorkItemContext with the set context
        """
        branch_name = GitContext.get_current_branch()
        work_item = self.index_manager.get_work_item(work_item_id)

        if link_to_branch and branch_name:
            self.index_manager.link_branch(branch_name, work_item_id)

        return WorkItemContext(
            work_item_id=work_item_id,
            work_item=work_item,
            source=ContextSource.MANUAL,
            branch_name=branch_name,
            confidence=1.0,
            raw_match=str(work_item_id)
        )

    def clear_context(self) -> None:
        """Clear any manually set context for current branch."""
        branch_name = GitContext.get_current_branch()
        if branch_name:
            self.index_manager.unlink_branch(branch_name)

    def detect_with_existence_check(self, config_path: str = ".ado/config.json") -> dict:
        """
        Detect context and check if the work item actually exists.

        Returns a dict with:
        - context: WorkItemContext
        - exists_in_cache: bool - Found in local cache
        - exists_in_ado: bool | None - Found in ADO (None if not checked)
        - can_create: bool - ID detected but item doesn't exist
        - suggested_title: str | None - Title derived from branch name
        - suggested_type: str | None - Work item type derived from branch prefix
        """
        context = self.detect()
        result = {
            "context": context,
            "exists_in_cache": False,
            "exists_in_ado": None,
            "can_create": False,
            "suggested_title": None,
            "suggested_type": None
        }

        if not context.has_context:
            return result

        # Check if exists in cache
        if context.work_item is not None:
            result["exists_in_cache"] = True
            result["exists_in_ado"] = True  # If in cache, assume exists
            return result

        # Not in cache - check ADO
        result["exists_in_ado"] = self._check_ado_exists(context.work_item_id, config_path)

        if not result["exists_in_ado"]:
            result["can_create"] = True
            # Extract suggested title and type from branch name
            if context.branch_name:
                result["suggested_title"] = self._extract_title_from_branch(context.branch_name)
                result["suggested_type"] = self._extract_type_from_branch(context.branch_name)

        return result

    def _check_ado_exists(self, work_item_id: int, config_path: str) -> bool:
        """Check if work item exists in ADO."""
        try:
            # Try using ado_client first
            from ado_client import ADOClient, ADOConfig, ADOError
            config = ADOConfig.from_file(config_path)
            client = ADOClient(config)
            item = client.get_work_item(work_item_id)
            return item is not None
        except ImportError:
            pass
        except Exception:
            pass

        # Fallback to CLI
        try:
            import json
            from pathlib import Path
            config = json.loads(Path(config_path).read_text())
            import subprocess
            result = subprocess.run(
                ["az", "boards", "work-item", "show",
                 "--organization", config["organization"],
                 "--id", str(work_item_id),
                 "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0
        except Exception:
            return False

    def _extract_title_from_branch(self, branch_name: str) -> str:
        """Extract a suggested title from branch name."""
        import re
        # Remove prefix (feature/, fix/, etc.)
        name = re.sub(r'^(?:feature|fix|bugfix|hotfix|release|user/[^/]+)/', '', branch_name)
        # Remove AB#1234 or bare number prefix
        name = re.sub(r'^(?:AB#)?\d+[-/]?', '', name)
        # Convert kebab-case to title case
        name = name.replace('-', ' ').replace('_', ' ')
        # Capitalize words
        name = ' '.join(word.capitalize() for word in name.split())
        return name if name else "New Work Item"

    def _extract_type_from_branch(self, branch_name: str) -> str:
        """Extract suggested work item type from branch prefix."""
        branch_lower = branch_name.lower()
        if branch_lower.startswith(('fix/', 'bugfix/', 'hotfix/')):
            return "Bug"
        elif branch_lower.startswith('feature/'):
            return "User Story"
        else:
            return "Task"


def format_context_summary(context: WorkItemContext) -> str:
    """Format context for human-readable display."""
    lines = []

    if context.has_context:
        lines.append(f"Work Item: AB#{context.work_item_id}")
        if context.work_item:
            lines.append(f"  Title: {context.work_item.title}")
            lines.append(f"  State: {context.work_item.state}")
            lines.append(f"  Type: {context.work_item.work_item_type}")
            if context.work_item.assigned_to:
                lines.append(f"  Assigned: {context.work_item.assigned_to}")
            if context.work_item.area_path:
                lines.append(f"  Area: {context.work_item.area_path}")
        lines.append(f"  Source: {context.source.value}")
        lines.append(f"  Confidence: {context.confidence:.0%}")
        if context.branch_name:
            lines.append(f"  Branch: {context.branch_name}")
        if context.suggested_area and not (context.work_item and context.work_item.area_path):
            lines.append(f"  Suggested Area: {context.suggested_area}")
    else:
        lines.append("No work item context detected")
        if context.branch_name:
            lines.append(f"  Current branch: {context.branch_name}")
            lines.append("  Tip: Use 'AB#1234' in branch name or set manually")
        if context.suggested_area:
            lines.append(f"  Suggested Area: {context.suggested_area}")

    return "\n".join(lines)


def format_existence_check_summary(check_result: dict) -> str:
    """Format existence check result for human-readable display."""
    lines = []
    context = check_result["context"]

    if not context.has_context:
        lines.append("No work item context detected")
        if context.branch_name:
            lines.append(f"  Current branch: {context.branch_name}")
            lines.append("  Tip: Use 'AB#1234' in branch name or set manually")
        if context.suggested_area:
            lines.append(f"  Suggested Area: {context.suggested_area}")
        return "\n".join(lines)

    lines.append(f"Work Item: AB#{context.work_item_id}")

    if check_result["exists_in_cache"]:
        # Item exists and is cached
        if context.work_item:
            lines.append(f"  Title: {context.work_item.title}")
            lines.append(f"  State: {context.work_item.state}")
            lines.append(f"  Type: {context.work_item.work_item_type}")
            if context.work_item.assigned_to:
                lines.append(f"  Assigned: {context.work_item.assigned_to}")
            if context.work_item.area_path:
                lines.append(f"  Area: {context.work_item.area_path}")
        lines.append(f"  Status: EXISTS (cached)")
    elif check_result["exists_in_ado"]:
        # Item exists in ADO but not cached
        lines.append(f"  Status: EXISTS (not cached - run sync to cache)")
    elif check_result["can_create"]:
        # Item doesn't exist - offer to create
        lines.append(f"  Status: DOES NOT EXIST")
        lines.append("")
        lines.append("  Work item AB#{} not found. Create it?".format(context.work_item_id))
        if check_result["suggested_title"]:
            lines.append(f"    Suggested title: {check_result['suggested_title']}")
        if check_result["suggested_type"]:
            lines.append(f"    Suggested type: {check_result['suggested_type']}")
        if context.suggested_area:
            lines.append(f"    Suggested area: {context.suggested_area}")
        lines.append("")
        lines.append("  To create, run:")
        lines.append(f"    python3 work_item_context.py --create-from-branch")
    else:
        lines.append(f"  Status: UNKNOWN (could not verify)")

    lines.append(f"  Source: {context.source.value}")
    lines.append(f"  Confidence: {context.confidence:.0%}")
    if context.branch_name:
        lines.append(f"  Branch: {context.branch_name}")
    if context.suggested_area and not (context.work_item and context.work_item.area_path):
        lines.append(f"  Suggested Area: {context.suggested_area}")

    return "\n".join(lines)


def create_work_item_from_context(
    config_path: str,
    work_item_id: int,
    title: str,
    work_item_type: str,
    description: Optional[str] = None,
    area_path: Optional[str] = None
) -> Optional[dict]:
    """
    Create a work item in ADO.

    Args:
        config_path: Path to ADO config file
        work_item_id: Work item ID (for reference, not used in creation)
        title: Work item title
        work_item_type: Type (Task, Bug, User Story, etc.)
        description: Optional description
        area_path: Optional area path to assign

    Returns the created work item dict or None on failure.
    """
    try:
        from pathlib import Path
        config = json.loads(Path(config_path).read_text())

        import subprocess
        cmd = [
            "az", "boards", "work-item", "create",
            "--organization", config["organization"],
            "--project", config["project"],
            "--type", work_item_type,
            "--title", title,
            "--output", "json"
        ]

        if description:
            cmd.extend(["--description", description])

        if area_path:
            cmd.extend(["--area", area_path])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            print(f"Error creating work item: {result.stderr}", file=sys.stderr)
            return None
    except Exception as e:
        print(f"Error creating work item: {e}", file=sys.stderr)
        return None


def main():
    """CLI for work item context detection."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Detect work item context from git branch/commits",
        epilog="""
Examples:
  %(prog)s                          # Detect context (includes suggested area)
  %(prog)s --check                  # Detect and verify work item exists
  %(prog)s --create-from-branch     # Create with auto-suggested area
  %(prog)s --create-from-branch --area "Project\\Core"  # Override area
  %(prog)s --set 1234               # Manually set context to work item
  %(prog)s --suggest-branch 1234    # Suggest branch name for work item
        """
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--config", "-c", default=".ado/config.json",
                       help="Path to ADO config file")
    parser.add_argument("--set", type=int, metavar="ID", help="Set work item context")
    parser.add_argument("--clear", action="store_true", help="Clear context")
    parser.add_argument("--check", action="store_true",
                       help="Check if detected work item exists in ADO")
    parser.add_argument("--create-from-branch", action="store_true",
                       help="Create work item from branch context if it doesn't exist")
    parser.add_argument("--title", type=str,
                       help="Override title when creating (with --create-from-branch)")
    parser.add_argument("--type", type=str, dest="work_type",
                       help="Override type when creating (Task, Bug, User Story)")
    parser.add_argument("--yes", "-y", action="store_true",
                       help="Skip confirmation when creating")
    parser.add_argument("--area", type=str,
                       help="Override area path when creating (with --create-from-branch)")
    parser.add_argument("--suggest-branch", type=int, metavar="ID",
                       help="Suggest branch name for work item")
    parser.add_argument("--parse-branch", type=str, metavar="NAME",
                       help="Parse a branch name for work item ID")
    parser.add_argument("--parse-commit", type=str, metavar="MSG",
                       help="Parse a commit message for work item IDs")

    args = parser.parse_args()

    if args.parse_branch:
        work_item_id, confidence, raw_match = BranchParser.parse(args.parse_branch)
        if args.json:
            print(json.dumps({
                "work_item_id": work_item_id,
                "confidence": confidence,
                "raw_match": raw_match
            }, indent=2))
        elif work_item_id:
            print(f"Work Item: AB#{work_item_id} (confidence: {confidence:.0%})")
        else:
            print("No work item found in branch name")
        return

    if args.parse_commit:
        refs = CommitParser.parse(args.parse_commit)
        if args.json:
            print(json.dumps([
                {"work_item_id": wid, "confidence": conf, "raw_match": raw}
                for wid, conf, raw in refs
            ], indent=2))
        elif refs:
            for wid, conf, raw in refs:
                print(f"Work Item: AB#{wid} (confidence: {conf:.0%}, match: '{raw}')")
        else:
            print("No work item references found in commit message")
        return

    if args.suggest_branch:
        index_manager = WorkItemIndexManager()
        work_item = index_manager.get_work_item(args.suggest_branch)
        suggested = BranchParser.suggest_branch_name(args.suggest_branch, work_item)
        print(suggested)
        return

    detector = WorkItemContextDetector()

    if args.clear:
        detector.clear_context()
        print("Context cleared for current branch")
        return

    if args.set:
        context = detector.set_context(args.set)
        if args.json:
            print(json.dumps(context.to_dict(), indent=2))
        else:
            print(f"Context set to AB#{args.set}")
            print(format_context_summary(context))
        return

    # Check existence and optionally create
    if args.check or args.create_from_branch:
        check_result = detector.detect_with_existence_check(args.config)
        context = check_result["context"]

        if args.json and not args.create_from_branch:
            output = {
                "work_item_id": context.work_item_id,
                "exists_in_cache": check_result["exists_in_cache"],
                "exists_in_ado": check_result["exists_in_ado"],
                "can_create": check_result["can_create"],
                "suggested_title": check_result["suggested_title"],
                "suggested_type": check_result["suggested_type"],
                "context": context.to_dict()
            }
            print(json.dumps(output, indent=2))
            return

        if args.create_from_branch:
            if not check_result["can_create"]:
                if check_result["exists_in_cache"] or check_result["exists_in_ado"]:
                    print(f"Work item AB#{context.work_item_id} already exists.")
                    print(format_context_summary(context))
                else:
                    print("No work item ID detected from branch name.")
                    print("Use a branch name like 'feature/AB#1234-description'")
                return

            # Prepare creation details
            title = args.title or check_result["suggested_title"] or "New Work Item"
            work_type = args.work_type or check_result["suggested_type"] or "Task"
            area = args.area or context.suggested_area

            print(f"Work item AB#{context.work_item_id} does not exist.")
            print("")
            print("Create new work item?")
            print(f"  Title: {title}")
            print(f"  Type: {work_type}")
            if area:
                print(f"  Area: {area}")
            print(f"  Branch: {context.branch_name}")
            print("")

            if not args.yes:
                try:
                    response = input("Create? [y/N]: ").strip().lower()
                    if response not in ('y', 'yes'):
                        print("Cancelled.")
                        return
                except (EOFError, KeyboardInterrupt):
                    print("\nCancelled.")
                    return

            # Create the work item
            print(f"Creating {work_type}: {title}...")
            created = create_work_item_from_context(
                args.config,
                context.work_item_id,
                title,
                work_type,
                area_path=area
            )

            if created:
                created_id = created.get("id")
                print(f"Created work item AB#{created_id}")

                # Update the index with the new item
                new_item = WorkItem(
                    id=created_id,
                    title=title,
                    state=created.get("fields", {}).get("System.State", "New"),
                    work_item_type=work_type,
                    assigned_to=None,
                    area_path=area,
                    url=created.get("url"),
                    last_fetched=datetime.utcnow()
                )
                detector.index_manager.upsert_work_item(new_item)
                detector.index_manager.link_branch(context.branch_name, created_id)
                detector.index_manager.save()
                print(f"Linked to branch: {context.branch_name}")

                if args.json:
                    print(json.dumps(created, indent=2))
            else:
                print("Failed to create work item.", file=sys.stderr)
                sys.exit(1)
            return

        # Just check (no create)
        print(format_existence_check_summary(check_result))
        return

    # Default: detect context
    context = detector.detect()

    if args.json:
        print(json.dumps(context.to_dict(), indent=2))
    else:
        print(format_context_summary(context))


if __name__ == "__main__":
    main()
