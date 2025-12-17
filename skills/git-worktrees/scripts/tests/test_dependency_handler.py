"""Tests for DependencyHandler."""

import tempfile
from pathlib import Path

import pytest

from dependency_handler import DependencyHandler


@pytest.fixture
def temp_project():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestDependencyDetection:
    """Tests for dependency detection."""

    def test_detect_nodejs_npm(self, temp_project):
        """Test detecting Node.js with npm."""
        (temp_project / "package.json").write_text('{"name": "test"}')
        (temp_project / "package-lock.json").write_text("{}")

        handler = DependencyHandler()
        deps = handler.detect_dependencies(str(temp_project))

        assert "nodejs" in deps
        assert deps["nodejs"] == "npm"

    def test_detect_nodejs_yarn(self, temp_project):
        """Test detecting Node.js with yarn."""
        (temp_project / "package.json").write_text('{"name": "test"}')
        (temp_project / "yarn.lock").write_text("")

        handler = DependencyHandler()
        deps = handler.detect_dependencies(str(temp_project))

        assert "nodejs" in deps
        assert deps["nodejs"] == "yarn"

    def test_detect_nodejs_pnpm(self, temp_project):
        """Test detecting Node.js with pnpm."""
        (temp_project / "package.json").write_text('{"name": "test"}')
        (temp_project / "pnpm-lock.yaml").write_text("")

        handler = DependencyHandler()
        deps = handler.detect_dependencies(str(temp_project))

        assert "nodejs" in deps
        assert deps["nodejs"] == "pnpm"

    def test_detect_python_pip(self, temp_project):
        """Test detecting Python with pip."""
        (temp_project / "requirements.txt").write_text("pytest>=7.0")

        handler = DependencyHandler()
        deps = handler.detect_dependencies(str(temp_project))

        assert "python" in deps
        assert deps["python"] == "pip"

    def test_detect_python_poetry(self, temp_project):
        """Test detecting Python with poetry."""
        (temp_project / "pyproject.toml").write_text(
            '[tool.poetry]\nname = "test"\nversion = "1.0.0"'
        )

        handler = DependencyHandler()
        deps = handler.detect_dependencies(str(temp_project))

        assert "python" in deps
        assert deps["python"] == "poetry"

    def test_detect_python_pipenv(self, temp_project):
        """Test detecting Python with pipenv."""
        (temp_project / "Pipfile").write_text("[packages]")

        handler = DependencyHandler()
        deps = handler.detect_dependencies(str(temp_project))

        assert "python" in deps
        assert deps["python"] == "pipenv"

    def test_detect_dotnet(self, temp_project):
        """Test detecting .NET projects."""
        (temp_project / "MyProject.csproj").write_text("<Project></Project>")

        handler = DependencyHandler()
        deps = handler.detect_dependencies(str(temp_project))

        assert "dotnet" in deps
        assert deps["dotnet"] == "nuget"

    def test_detect_dotnet_sln(self, temp_project):
        """Test detecting .NET solution files."""
        (temp_project / "MySolution.sln").write_text("Microsoft Visual Studio Solution File")

        handler = DependencyHandler()
        deps = handler.detect_dependencies(str(temp_project))

        assert "dotnet" in deps
        assert deps["dotnet"] == "nuget"

    def test_detect_rust(self, temp_project):
        """Test detecting Rust projects."""
        (temp_project / "Cargo.toml").write_text('[package]\nname = "test"')

        handler = DependencyHandler()
        deps = handler.detect_dependencies(str(temp_project))

        assert "rust" in deps
        assert deps["rust"] == "cargo"

    def test_detect_go(self, temp_project):
        """Test detecting Go projects."""
        (temp_project / "go.mod").write_text("module test")

        handler = DependencyHandler()
        deps = handler.detect_dependencies(str(temp_project))

        assert "go" in deps
        assert deps["go"] == "go"

    def test_detect_ruby(self, temp_project):
        """Test detecting Ruby projects."""
        (temp_project / "Gemfile").write_text('source "https://rubygems.org"')

        handler = DependencyHandler()
        deps = handler.detect_dependencies(str(temp_project))

        assert "ruby" in deps
        assert deps["ruby"] == "bundler"

    def test_detect_java_maven(self, temp_project):
        """Test detecting Java with Maven."""
        (temp_project / "pom.xml").write_text("<project></project>")

        handler = DependencyHandler()
        deps = handler.detect_dependencies(str(temp_project))

        assert "java" in deps
        assert deps["java"] == "maven"

    def test_detect_java_gradle(self, temp_project):
        """Test detecting Java with Gradle."""
        (temp_project / "build.gradle").write_text("plugins { }")

        handler = DependencyHandler()
        deps = handler.detect_dependencies(str(temp_project))

        assert "java" in deps
        assert deps["java"] == "gradle"

    def test_detect_kotlin_gradle(self, temp_project):
        """Test detecting Kotlin with Gradle."""
        (temp_project / "build.gradle.kts").write_text("plugins { }")

        handler = DependencyHandler()
        deps = handler.detect_dependencies(str(temp_project))

        assert "java" in deps
        assert deps["java"] == "gradle"

    def test_detect_multiple(self, temp_project):
        """Test detecting multiple dependency systems."""
        (temp_project / "package.json").write_text('{"name": "test"}')
        (temp_project / "requirements.txt").write_text("pytest")

        handler = DependencyHandler()
        deps = handler.detect_dependencies(str(temp_project))

        assert "nodejs" in deps
        assert "python" in deps

    def test_detect_empty_project(self, temp_project):
        """Test detecting no dependencies in empty project."""
        handler = DependencyHandler()
        deps = handler.detect_dependencies(str(temp_project))

        assert len(deps) == 0
