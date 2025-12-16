#!/usr/bin/env python3
"""
Area Advisor - Compare code structure to ADO areas and suggest improvements.

Analyzes existing Azure DevOps area structure against codebase components,
applies best practice rules, and generates actionable recommendations.

Usage:
    python area_advisor.py                            # Full analysis and recommendations
    python area_advisor.py --check-only               # Just check for anti-patterns
    python area_advisor.py --suggest-for-path src/Orders  # Suggest area for path
    python area_advisor.py --output report.json       # Save full report
"""

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from area_analyzer import CodebaseAnalyzer, CodebaseAnalysis, CodeComponent


class RecommendationType(Enum):
    """Type of recommendation."""
    CREATE = "create"
    RENAME = "rename"
    RESTRUCTURE = "restructure"
    ARCHIVE = "archive"
    MERGE = "merge"


class Severity(Enum):
    """Severity of an issue or recommendation."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AntiPatternType(Enum):
    """Types of area anti-patterns."""
    TEAM_NAMED = "team_named"
    TECH_BASED = "tech_based"
    TOO_FLAT = "too_flat"
    TOO_DEEP = "too_deep"
    ORPHANED = "orphaned"
    INCONSISTENT_NAMING = "inconsistent_naming"
    DUPLICATE_CONCEPT = "duplicate_concept"
    MISSING_STRUCTURE = "missing_structure"


@dataclass
class ADOArea:
    """An Azure DevOps area."""
    id: int
    name: str
    path: str
    has_children: bool
    children: List["ADOArea"] = field(default_factory=list)
    work_item_count: Optional[int] = None
    recent_activity: Optional[datetime] = None

    @property
    def depth(self) -> int:
        """Calculate depth of this area in hierarchy."""
        return self.path.count('\\')

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "has_children": self.has_children,
            "depth": self.depth,
            "children": [c.to_dict() for c in self.children],
            "work_item_count": self.work_item_count,
            "recent_activity": self.recent_activity.isoformat() if self.recent_activity else None
        }


@dataclass
class AntiPattern:
    """A detected anti-pattern in area structure."""
    pattern_type: AntiPatternType
    severity: Severity
    area_path: str
    description: str
    recommendation: str
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "pattern_type": self.pattern_type.value,
            "severity": self.severity.value,
            "area_path": self.area_path,
            "description": self.description,
            "recommendation": self.recommendation,
            "evidence": self.evidence
        }


@dataclass
class Recommendation:
    """A recommendation for area improvement."""
    rec_type: RecommendationType
    severity: Severity
    title: str
    description: str
    current_state: Optional[str]
    proposed_state: str
    rationale: str
    effort: str  # "low", "medium", "high"
    impact: str  # "low", "medium", "high"
    affected_items: int = 0
    steps: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "type": self.rec_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "current_state": self.current_state,
            "proposed_state": self.proposed_state,
            "rationale": self.rationale,
            "effort": self.effort,
            "impact": self.impact,
            "affected_items": self.affected_items,
            "steps": self.steps
        }


@dataclass
class GapAnalysis:
    """Analysis of gaps between code and areas."""
    components_without_areas: List[CodeComponent]
    areas_without_components: List[ADOArea]
    mismatched_mappings: List[Tuple[CodeComponent, ADOArea]]

    def to_dict(self) -> dict:
        return {
            "components_without_areas": [c.to_dict() for c in self.components_without_areas],
            "areas_without_components": [a.to_dict() for a in self.areas_without_components],
            "mismatched_mappings": [
                {"component": c.to_dict(), "area": a.to_dict()}
                for c, a in self.mismatched_mappings
            ]
        }


@dataclass
class AreaAdvisoryReport:
    """Complete advisory report."""
    analysis_timestamp: datetime
    codebase_path: str
    project_name: str
    organization: str

    # Analysis results
    existing_areas: List[ADOArea]
    codebase_analysis: CodebaseAnalysis
    gap_analysis: GapAnalysis
    anti_patterns: List[AntiPattern]
    recommendations: List[Recommendation]

    # Summary scores
    health_score: float  # 0-100
    coverage_score: float  # 0-100
    structure_score: float  # 0-100

    def to_dict(self) -> dict:
        return {
            "analysis_timestamp": self.analysis_timestamp.isoformat(),
            "codebase_path": self.codebase_path,
            "project_name": self.project_name,
            "organization": self.organization,
            "existing_areas": [a.to_dict() for a in self.existing_areas],
            "codebase_analysis": self.codebase_analysis.to_dict(),
            "gap_analysis": self.gap_analysis.to_dict(),
            "anti_patterns": [a.to_dict() for a in self.anti_patterns],
            "recommendations": [r.to_dict() for r in self.recommendations],
            "health_score": self.health_score,
            "coverage_score": self.coverage_score,
            "structure_score": self.structure_score
        }


class ADOAreaFetcher:
    """Fetch areas from Azure DevOps."""

    def __init__(self, config_path: str = ".ado/config.json"):
        self.config = self._load_config(config_path)

    def _load_config(self, config_path: str) -> dict:
        """Load ADO configuration."""
        try:
            return json.loads(Path(config_path).read_text())
        except Exception:
            return {}

    def fetch_areas(self) -> List[ADOArea]:
        """Fetch all areas from ADO."""
        if not self.config:
            return []

        try:
            result = subprocess.run(
                ["az", "boards", "area", "project", "list",
                 "--organization", self.config["organization"],
                 "--project", self.config["project"],
                 "--depth", "5",
                 "--output", "json"],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                print(f"Warning: Could not fetch areas: {result.stderr}")
                return []

            data = json.loads(result.stdout)
            return self._parse_area_tree(data)

        except Exception as e:
            print(f"Warning: Could not fetch areas: {e}")
            return []

    def _parse_area_tree(self, data: dict, parent_path: str = "") -> List[ADOArea]:
        """Parse area tree from ADO response."""
        areas = []

        if not data:
            return areas

        # Handle both list and single item responses
        items = data if isinstance(data, list) else [data]

        for item in items:
            area = ADOArea(
                id=item.get('id', 0),
                name=item.get('name', ''),
                path=item.get('path', '').replace('\\Area\\', '\\'),
                has_children=item.get('hasChildren', False),
            )

            # Recursively parse children
            if 'children' in item:
                area.children = self._parse_area_tree(item['children'], area.path)

            areas.append(area)

        return areas

    def get_area_work_item_counts(self, areas: List[ADOArea]) -> Dict[str, int]:
        """Get work item counts per area (simplified)."""
        # This would require additional queries - return empty for now
        return {}


class AntiPatternDetector:
    """Detect anti-patterns in area structure."""

    # Known team name patterns
    TEAM_PATTERNS = [
        r'^team[-_\s]',
        r'[-_\s]team$',
        r'^(alpha|beta|gamma|delta|phoenix|tiger|eagle)$',
        r'^squad[-_\s]',
        r'[-_\s]squad$',
    ]

    # Technology-based naming (anti-pattern for domain areas)
    TECH_NAMES = {
        'api', 'apis', 'backend', 'frontend', 'database', 'db',
        'ui', 'web', 'mobile', 'desktop', 'server', 'client',
        'microservices', 'services', 'infrastructure', 'infra',
        'devops', 'cicd', 'pipeline', 'deploy', 'cloud',
        'dotnet', 'java', 'python', 'node', 'react', 'angular',
    }

    def detect(self, areas: List[ADOArea], project_name: str) -> List[AntiPattern]:
        """Detect anti-patterns in area structure."""
        patterns = []

        flat_areas = self._flatten_areas(areas)

        patterns.extend(self._check_team_naming(flat_areas))
        patterns.extend(self._check_tech_naming(flat_areas))
        patterns.extend(self._check_depth(flat_areas))
        patterns.extend(self._check_flat_structure(flat_areas, project_name))
        patterns.extend(self._check_inconsistent_naming(flat_areas))
        patterns.extend(self._check_duplicates(flat_areas))

        return patterns

    def _flatten_areas(self, areas: List[ADOArea]) -> List[ADOArea]:
        """Flatten area hierarchy into a list."""
        result = []
        for area in areas:
            result.append(area)
            if area.children:
                result.extend(self._flatten_areas(area.children))
        return result

    def _check_team_naming(self, areas: List[ADOArea]) -> List[AntiPattern]:
        """Check for team-named areas."""
        patterns = []

        for area in areas:
            name_lower = area.name.lower()

            for pattern in self.TEAM_PATTERNS:
                if re.search(pattern, name_lower, re.IGNORECASE):
                    patterns.append(AntiPattern(
                        pattern_type=AntiPatternType.TEAM_NAMED,
                        severity=Severity.MEDIUM,
                        area_path=area.path,
                        description=f"Area '{area.name}' appears to be named after a team",
                        recommendation="Rename to reflect the domain/product area, not the team. "
                                      "Teams change; domains are stable.",
                        evidence=[f"Matched pattern: {pattern}"]
                    ))
                    break

        return patterns

    def _check_tech_naming(self, areas: List[ADOArea]) -> List[AntiPattern]:
        """Check for technology-based naming."""
        patterns = []

        for area in areas:
            name_lower = area.name.lower()

            # Only flag if it's a top-level tech name (not a category like "Platform\Infrastructure")
            if name_lower in self.TECH_NAMES and area.depth <= 2:
                patterns.append(AntiPattern(
                    pattern_type=AntiPatternType.TECH_BASED,
                    severity=Severity.LOW,
                    area_path=area.path,
                    description=f"Area '{area.name}' is technology-based rather than domain-based",
                    recommendation="Consider organizing by business domain (Orders, Customers) "
                                  "rather than technology layer (API, Database). "
                                  "Exception: Platform/Infrastructure areas are acceptable.",
                    evidence=[f"Name matches tech term: {name_lower}"]
                ))

        return patterns

    def _check_depth(self, areas: List[ADOArea]) -> List[AntiPattern]:
        """Check for areas that are too deep."""
        patterns = []

        for area in areas:
            if area.depth > 4:
                patterns.append(AntiPattern(
                    pattern_type=AntiPatternType.TOO_DEEP,
                    severity=Severity.MEDIUM,
                    area_path=area.path,
                    description=f"Area is {area.depth} levels deep (max recommended: 4)",
                    recommendation="Flatten hierarchy. Deep nesting makes navigation difficult "
                                  "and often indicates over-engineering.",
                    evidence=[f"Depth: {area.depth}"]
                ))

        return patterns

    def _check_flat_structure(self, areas: List[ADOArea], project_name: str) -> List[AntiPattern]:
        """Check for overly flat structure."""
        patterns = []

        # Count areas at each depth
        depth_counts = {}
        for area in areas:
            depth_counts[area.depth] = depth_counts.get(area.depth, 0) + 1

        # If most areas are at depth 1 (directly under project), structure is too flat
        root_areas = depth_counts.get(1, 0)
        total_areas = len(areas)

        if total_areas > 5 and root_areas > 0 and (root_areas / total_areas) > 0.8:
            patterns.append(AntiPattern(
                pattern_type=AntiPatternType.TOO_FLAT,
                severity=Severity.MEDIUM,
                area_path=project_name,
                description=f"{root_areas} of {total_areas} areas are at root level",
                recommendation="Create category areas (Platform, Core, Integrations) to group "
                              "related components. This improves navigation and reporting.",
                evidence=[f"Root areas: {root_areas}/{total_areas}"]
            ))

        return patterns

    def _check_inconsistent_naming(self, areas: List[ADOArea]) -> List[AntiPattern]:
        """Check for inconsistent naming conventions."""
        patterns = []

        naming_styles = {
            'pascal': 0,  # OrderProcessing
            'kebab': 0,   # order-processing
            'snake': 0,   # order_processing
            'space': 0,   # Order Processing
        }

        for area in areas:
            name = area.name
            if re.match(r'^[A-Z][a-z]+([A-Z][a-z]+)+$', name):
                naming_styles['pascal'] += 1
            elif '-' in name:
                naming_styles['kebab'] += 1
            elif '_' in name:
                naming_styles['snake'] += 1
            elif ' ' in name:
                naming_styles['space'] += 1

        # Find dominant style
        total = sum(naming_styles.values())
        if total > 3:
            dominant = max(naming_styles, key=naming_styles.get)
            dominant_count = naming_styles[dominant]

            if dominant_count < total * 0.7:
                patterns.append(AntiPattern(
                    pattern_type=AntiPatternType.INCONSISTENT_NAMING,
                    severity=Severity.LOW,
                    area_path="(multiple)",
                    description="Inconsistent naming conventions across areas",
                    recommendation=f"Standardize on {dominant} case for consistency. "
                                  "Current mix: " + ", ".join(f"{k}={v}" for k, v in naming_styles.items() if v > 0),
                    evidence=[f"Style counts: {naming_styles}"]
                ))

        return patterns

    def _check_duplicates(self, areas: List[ADOArea]) -> List[AntiPattern]:
        """Check for duplicate/similar area concepts."""
        patterns = []

        # Normalize names and look for similar concepts
        normalized_names: Dict[str, List[str]] = {}

        for area in areas:
            # Normalize: lowercase, remove common suffixes
            normalized = area.name.lower()
            normalized = re.sub(r'(service|module|component|area|management)s?$', '', normalized)
            normalized = re.sub(r'[-_\s]', '', normalized)

            if normalized not in normalized_names:
                normalized_names[normalized] = []
            normalized_names[normalized].append(area.path)

        # Flag duplicates
        for normalized, paths in normalized_names.items():
            if len(paths) > 1 and len(normalized) > 2:
                patterns.append(AntiPattern(
                    pattern_type=AntiPatternType.DUPLICATE_CONCEPT,
                    severity=Severity.MEDIUM,
                    area_path=paths[0],
                    description=f"Multiple areas seem to represent the same concept: {', '.join(paths)}",
                    recommendation="Consider merging these areas or clarifying their distinct purposes.",
                    evidence=paths
                ))

        return patterns


class GapAnalyzer:
    """Analyze gaps between code components and ADO areas."""

    def analyze(self, components: List[CodeComponent], areas: List[ADOArea]) -> GapAnalysis:
        """Analyze gaps between code and areas."""
        flat_areas = self._flatten_areas(areas)

        # Normalize names for comparison
        area_names = {self._normalize(a.name): a for a in flat_areas}
        component_names = {self._normalize(c.name): c for c in components}

        # Find components without matching areas
        components_without_areas = []
        for norm_name, component in component_names.items():
            if norm_name not in area_names and component.confidence >= 0.5:
                components_without_areas.append(component)

        # Find areas without matching components
        areas_without_components = []
        for norm_name, area in area_names.items():
            if norm_name not in component_names:
                # Skip root and category areas
                if area.depth >= 2 and not area.has_children:
                    areas_without_components.append(area)

        # Find mismatched mappings (same concept, different structure)
        mismatched = []
        # This would require more sophisticated analysis

        return GapAnalysis(
            components_without_areas=components_without_areas,
            areas_without_components=areas_without_components,
            mismatched_mappings=mismatched
        )

    def _flatten_areas(self, areas: List[ADOArea]) -> List[ADOArea]:
        """Flatten area hierarchy."""
        result = []
        for area in areas:
            result.append(area)
            if area.children:
                result.extend(self._flatten_areas(area.children))
        return result

    def _normalize(self, name: str) -> str:
        """Normalize a name for comparison."""
        name = name.lower()
        name = re.sub(r'[-_\s]', '', name)
        name = re.sub(r'(service|module|component|area|management)s?$', '', name)
        return name


class RecommendationGenerator:
    """Generate recommendations based on analysis."""

    def generate(
        self,
        codebase_analysis: CodebaseAnalysis,
        existing_areas: List[ADOArea],
        gap_analysis: GapAnalysis,
        anti_patterns: List[AntiPattern],
        project_name: str
    ) -> List[Recommendation]:
        """Generate recommendations."""
        recommendations = []

        # Recommendations for missing areas
        for component in gap_analysis.components_without_areas:
            suggested_path = self._suggest_area_path(component, codebase_analysis, project_name)

            recommendations.append(Recommendation(
                rec_type=RecommendationType.CREATE,
                severity=Severity.MEDIUM if component.confidence >= 0.7 else Severity.LOW,
                title=f"Create area for {component.name}",
                description=f"Component '{component.name}' detected in code but has no corresponding area",
                current_state=None,
                proposed_state=suggested_path,
                rationale=f"Detected from {component.source} with {component.confidence:.0%} confidence. "
                         f"Creating this area will enable proper work item categorization.",
                effort="low",
                impact="medium",
                steps=[
                    f"Create area: {suggested_path}",
                    "Update work item templates to include new area option",
                    "Assign existing related work items to new area"
                ]
            ))

        # Recommendations for anti-patterns
        for pattern in anti_patterns:
            if pattern.severity in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM):
                rec = self._anti_pattern_to_recommendation(pattern, project_name)
                if rec:
                    recommendations.append(rec)

        # Recommendations for orphaned areas
        for area in gap_analysis.areas_without_components:
            recommendations.append(Recommendation(
                rec_type=RecommendationType.ARCHIVE,
                severity=Severity.LOW,
                title=f"Review area '{area.name}' for archival",
                description=f"Area '{area.path}' has no corresponding code component",
                current_state=area.path,
                proposed_state="(archived or merged)",
                rationale="This area may be obsolete if no code maps to it. "
                         "Review recent work items before archiving.",
                effort="low",
                impact="low",
                steps=[
                    f"Check work items in {area.path} for recent activity",
                    "If no recent activity, move items to parent area",
                    "Archive or delete the area"
                ]
            ))

        # Sort by severity and impact
        recommendations.sort(
            key=lambda r: (
                list(Severity).index(r.severity),
                {'high': 0, 'medium': 1, 'low': 2}.get(r.impact, 2)
            )
        )

        return recommendations

    def _suggest_area_path(
        self,
        component: CodeComponent,
        analysis: CodebaseAnalysis,
        project_name: str
    ) -> str:
        """Suggest an area path for a component."""
        # Use the suggested structure from analysis
        for category, areas in analysis.suggested_area_structure.items():
            for area in areas:
                if component.name.lower() in area.lower():
                    return area

        # Default: put under Core
        clean_name = component.suggested_area_path()
        return f"{project_name}\\Core\\{clean_name}"

    def _anti_pattern_to_recommendation(
        self,
        pattern: AntiPattern,
        project_name: str
    ) -> Optional[Recommendation]:
        """Convert anti-pattern to recommendation."""
        if pattern.pattern_type == AntiPatternType.TEAM_NAMED:
            return Recommendation(
                rec_type=RecommendationType.RENAME,
                severity=pattern.severity,
                title=f"Rename team-based area '{pattern.area_path}'",
                description=pattern.description,
                current_state=pattern.area_path,
                proposed_state="(domain-based name)",
                rationale=pattern.recommendation,
                effort="medium",
                impact="medium",
                steps=[
                    "Identify the domain this team works on",
                    "Create new area with domain-based name",
                    "Migrate work items to new area",
                    "Archive old area after transition period"
                ]
            )

        if pattern.pattern_type == AntiPatternType.TOO_FLAT:
            return Recommendation(
                rec_type=RecommendationType.RESTRUCTURE,
                severity=pattern.severity,
                title="Add category structure to flatten root",
                description=pattern.description,
                current_state=pattern.area_path,
                proposed_state=f"{project_name}\\[Platform|Core|Integrations]\\...",
                rationale=pattern.recommendation,
                effort="high",
                impact="high",
                steps=[
                    "Identify logical groupings (Platform, Core, Integrations, etc.)",
                    "Create category areas",
                    "Move existing areas under appropriate categories",
                    "Update queries and dashboards"
                ]
            )

        if pattern.pattern_type == AntiPatternType.TOO_DEEP:
            return Recommendation(
                rec_type=RecommendationType.RESTRUCTURE,
                severity=pattern.severity,
                title=f"Flatten deep area hierarchy at '{pattern.area_path}'",
                description=pattern.description,
                current_state=pattern.area_path,
                proposed_state="(flattened to max 4 levels)",
                rationale=pattern.recommendation,
                effort="medium",
                impact="medium",
                steps=[
                    "Identify which levels can be merged",
                    "Create flatter structure",
                    "Migrate work items",
                    "Archive deep areas"
                ]
            )

        if pattern.pattern_type == AntiPatternType.DUPLICATE_CONCEPT:
            return Recommendation(
                rec_type=RecommendationType.MERGE,
                severity=pattern.severity,
                title=f"Merge duplicate concept areas",
                description=pattern.description,
                current_state=", ".join(pattern.evidence),
                proposed_state="(single unified area)",
                rationale=pattern.recommendation,
                effort="medium",
                impact="medium",
                steps=[
                    "Decide on canonical name",
                    "Create unified area if needed",
                    "Migrate work items from all duplicates",
                    "Archive duplicate areas"
                ]
            )

        return None


class HealthScoreCalculator:
    """Calculate health scores for area structure."""

    def calculate(
        self,
        areas: List[ADOArea],
        components: List[CodeComponent],
        gap_analysis: GapAnalysis,
        anti_patterns: List[AntiPattern]
    ) -> Tuple[float, float, float]:
        """Calculate health, coverage, and structure scores."""

        # Coverage score: what % of components have areas
        total_components = len(components)
        components_with_areas = total_components - len(gap_analysis.components_without_areas)
        coverage = (components_with_areas / total_components * 100) if total_components > 0 else 100

        # Structure score: penalize anti-patterns
        pattern_penalties = {
            Severity.CRITICAL: 20,
            Severity.HIGH: 10,
            Severity.MEDIUM: 5,
            Severity.LOW: 2,
            Severity.INFO: 0
        }
        penalty = sum(pattern_penalties.get(p.severity, 0) for p in anti_patterns)
        structure = max(0, 100 - penalty)

        # Overall health: weighted average
        health = (coverage * 0.4 + structure * 0.6)

        return health, coverage, structure


class AreaAdvisor:
    """Main advisor that coordinates analysis and recommendations."""

    def __init__(self, config_path: str = ".ado/config.json", codebase_path: str = "."):
        self.config_path = config_path
        self.codebase_path = codebase_path
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """Load ADO configuration."""
        try:
            return json.loads(Path(self.config_path).read_text())
        except Exception:
            return {}

    def analyze(self) -> AreaAdvisoryReport:
        """Perform complete analysis and generate report."""
        # Fetch existing areas from ADO
        fetcher = ADOAreaFetcher(self.config_path)
        existing_areas = fetcher.fetch_areas()

        # Analyze codebase
        codebase_analyzer = CodebaseAnalyzer(self.codebase_path)
        codebase_analysis = codebase_analyzer.analyze()

        # Detect anti-patterns
        project_name = self.config.get('project', Path(self.codebase_path).name)
        anti_detector = AntiPatternDetector()
        anti_patterns = anti_detector.detect(existing_areas, project_name)

        # Gap analysis
        gap_analyzer = GapAnalyzer()
        gap_analysis = gap_analyzer.analyze(codebase_analysis.components, existing_areas)

        # Generate recommendations
        rec_generator = RecommendationGenerator()
        recommendations = rec_generator.generate(
            codebase_analysis,
            existing_areas,
            gap_analysis,
            anti_patterns,
            project_name
        )

        # Calculate scores
        score_calc = HealthScoreCalculator()
        health, coverage, structure = score_calc.calculate(
            existing_areas,
            codebase_analysis.components,
            gap_analysis,
            anti_patterns
        )

        return AreaAdvisoryReport(
            analysis_timestamp=datetime.now(timezone.utc),
            codebase_path=str(Path(self.codebase_path).resolve()),
            project_name=project_name,
            organization=self.config.get('organization', ''),
            existing_areas=existing_areas,
            codebase_analysis=codebase_analysis,
            gap_analysis=gap_analysis,
            anti_patterns=anti_patterns,
            recommendations=recommendations,
            health_score=health,
            coverage_score=coverage,
            structure_score=structure
        )

    def suggest_area_for_path(self, file_path: str) -> Optional[str]:
        """Suggest the best area for a given file path."""
        # Quick analysis of just the path
        path = Path(file_path)
        parts = path.parts

        # Look for domain-indicating directory names
        domain_dirs = []
        for i, part in enumerate(parts):
            part_lower = part.lower()
            if part_lower not in {'src', 'lib', 'packages', 'apps', 'services', 'test', 'tests'}:
                if not part.startswith('.') and not part.startswith('_'):
                    domain_dirs.append(part)

        if domain_dirs:
            # Use first meaningful directory as component
            component_name = domain_dirs[0]

            # Clean up the name
            component_name = re.sub(r'[-_]', '', component_name)
            component_name = component_name[0].upper() + component_name[1:] if component_name else ''

            project_name = self.config.get('project', '')
            if project_name:
                return f"{project_name}\\Core\\{component_name}"
            return f"Core\\{component_name}"

        return None


def format_report(report: AreaAdvisoryReport) -> str:
    """Format report for human-readable display."""
    lines = []

    # Header
    lines.append("=" * 70)
    lines.append("AREA ADVISORY REPORT")
    lines.append("=" * 70)
    lines.append(f"Project: {report.project_name}")
    lines.append(f"Generated: {report.analysis_timestamp.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")

    # Health scores
    lines.append("HEALTH SCORES")
    lines.append("-" * 40)

    def score_bar(score: float) -> str:
        filled = int(score / 10)
        return f"[{'█' * filled}{'░' * (10 - filled)}] {score:.0f}%"

    lines.append(f"Overall Health:  {score_bar(report.health_score)}")
    lines.append(f"Coverage:        {score_bar(report.coverage_score)}")
    lines.append(f"Structure:       {score_bar(report.structure_score)}")
    lines.append("")

    # Existing areas summary
    lines.append("EXISTING AREAS")
    lines.append("-" * 40)
    flat_areas = []

    def flatten(areas, depth=0):
        for area in areas:
            flat_areas.append((area, depth))
            if area.children:
                flatten(area.children, depth + 1)

    flatten(report.existing_areas)
    for area, depth in flat_areas[:20]:  # Limit display
        indent = "  " * depth
        lines.append(f"{indent}├── {area.name}")
    if len(flat_areas) > 20:
        lines.append(f"  ... and {len(flat_areas) - 20} more")
    lines.append("")

    # Anti-patterns
    if report.anti_patterns:
        lines.append("ANTI-PATTERNS DETECTED")
        lines.append("-" * 40)
        for pattern in report.anti_patterns:
            severity_icon = {
                Severity.CRITICAL: "🔴",
                Severity.HIGH: "🟠",
                Severity.MEDIUM: "🟡",
                Severity.LOW: "🟢",
                Severity.INFO: "ℹ️"
            }.get(pattern.severity, "❓")

            lines.append(f"{severity_icon} [{pattern.pattern_type.value}] {pattern.area_path}")
            lines.append(f"   {pattern.description}")
            lines.append(f"   → {pattern.recommendation}")
            lines.append("")

    # Gap analysis
    lines.append("GAP ANALYSIS")
    lines.append("-" * 40)

    if report.gap_analysis.components_without_areas:
        lines.append("Components needing areas:")
        for comp in report.gap_analysis.components_without_areas[:10]:
            lines.append(f"  • {comp.name} ({comp.confidence:.0%} confidence)")
        if len(report.gap_analysis.components_without_areas) > 10:
            lines.append(f"  ... and {len(report.gap_analysis.components_without_areas) - 10} more")
    else:
        lines.append("✓ All detected components have corresponding areas")

    lines.append("")

    if report.gap_analysis.areas_without_components:
        lines.append("Areas without code components (may be obsolete):")
        for area in report.gap_analysis.areas_without_components[:10]:
            lines.append(f"  • {area.path}")
        if len(report.gap_analysis.areas_without_components) > 10:
            lines.append(f"  ... and {len(report.gap_analysis.areas_without_components) - 10} more")
        lines.append("")

    # Recommendations
    if report.recommendations:
        lines.append("RECOMMENDATIONS")
        lines.append("-" * 40)

        for i, rec in enumerate(report.recommendations[:10], 1):
            severity_icon = {
                Severity.CRITICAL: "🔴",
                Severity.HIGH: "🟠",
                Severity.MEDIUM: "🟡",
                Severity.LOW: "🟢",
            }.get(rec.severity, "ℹ️")

            lines.append(f"{i}. {severity_icon} [{rec.rec_type.value.upper()}] {rec.title}")
            lines.append(f"   {rec.description}")
            if rec.proposed_state:
                lines.append(f"   Proposed: {rec.proposed_state}")
            lines.append(f"   Effort: {rec.effort} | Impact: {rec.impact}")
            lines.append("")

        if len(report.recommendations) > 10:
            lines.append(f"... and {len(report.recommendations) - 10} more recommendations")
            lines.append("")

    # Suggested structure
    lines.append("SUGGESTED AREA STRUCTURE")
    lines.append("-" * 40)
    for category, areas in report.codebase_analysis.suggested_area_structure.items():
        lines.append(f"  {category}")
        for area in areas[:5]:
            area_name = area.split('\\')[-1]
            lines.append(f"    └── {area_name}")
        if len(areas) > 5:
            lines.append(f"    └── ... and {len(areas) - 5} more")
    lines.append("")

    lines.append("=" * 70)

    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze ADO areas and suggest improvements",
        epilog="""
Examples:
  %(prog)s                              # Full analysis
  %(prog)s --check-only                 # Just check anti-patterns
  %(prog)s --suggest-for-path src/Orders/OrderService.cs
  %(prog)s --output report.json         # Save to file
        """
    )
    parser.add_argument("--config", "-c", default=".ado/config.json",
                        help="Path to ADO config file")
    parser.add_argument("--path", "-p", default=".",
                        help="Path to codebase (default: current directory)")
    parser.add_argument("--output", "-o",
                        help="Output file for JSON report")
    parser.add_argument("--format", "-f", choices=["text", "json"], default="text",
                        help="Output format (default: text)")
    parser.add_argument("--check-only", action="store_true",
                        help="Only check for anti-patterns, skip recommendations")
    parser.add_argument("--suggest-for-path", metavar="PATH",
                        help="Suggest area for a specific file path")

    args = parser.parse_args()

    advisor = AreaAdvisor(args.config, args.path)

    # Quick suggestion mode
    if args.suggest_for_path:
        suggestion = advisor.suggest_area_for_path(args.suggest_for_path)
        if suggestion:
            print(f"Suggested area: {suggestion}")
        else:
            print("Could not determine appropriate area for this path")
        return

    # Full analysis
    report = advisor.analyze()

    # Output
    if args.format == "json" or args.output:
        output = json.dumps(report.to_dict(), indent=2)
        if args.output:
            Path(args.output).write_text(output)
            print(f"Report saved to {args.output}")
        else:
            print(output)
    else:
        print(format_report(report))


if __name__ == "__main__":
    main()
