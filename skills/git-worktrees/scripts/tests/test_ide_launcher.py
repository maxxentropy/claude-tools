"""Tests for IDELauncher."""

import tempfile
from pathlib import Path

import pytest

from ide_launcher import IDELauncher


@pytest.fixture
def temp_project():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestProjectTypeDetection:
    """Tests for project type detection."""

    def test_detect_dotnet(self, temp_project):
        """Test detecting .NET projects."""
        (temp_project / "MyProject.csproj").write_text("<Project></Project>")

        launcher = IDELauncher()
        project_type = launcher.detect_project_type(str(temp_project))

        assert project_type == "dotnet"

    def test_detect_dotnet_sln(self, temp_project):
        """Test detecting .NET solution files."""
        (temp_project / "MySolution.sln").write_text("Microsoft Visual Studio Solution File")

        launcher = IDELauncher()
        project_type = launcher.detect_project_type(str(temp_project))

        assert project_type == "dotnet"

    def test_detect_python_pyproject(self, temp_project):
        """Test detecting Python with pyproject.toml."""
        (temp_project / "pyproject.toml").write_text('[project]\nname = "test"')

        launcher = IDELauncher()
        project_type = launcher.detect_project_type(str(temp_project))

        assert project_type == "python"

    def test_detect_python_requirements(self, temp_project):
        """Test detecting Python with requirements.txt."""
        (temp_project / "requirements.txt").write_text("pytest")

        launcher = IDELauncher()
        project_type = launcher.detect_project_type(str(temp_project))

        assert project_type == "python"

    def test_detect_nodejs(self, temp_project):
        """Test detecting Node.js projects."""
        (temp_project / "package.json").write_text('{"name": "test"}')

        launcher = IDELauncher()
        project_type = launcher.detect_project_type(str(temp_project))

        assert project_type == "nodejs"

    def test_detect_java(self, temp_project):
        """Test detecting Java projects."""
        (temp_project / "pom.xml").write_text("<project></project>")

        launcher = IDELauncher()
        project_type = launcher.detect_project_type(str(temp_project))

        assert project_type == "java"

    def test_detect_go(self, temp_project):
        """Test detecting Go projects."""
        (temp_project / "go.mod").write_text("module test")

        launcher = IDELauncher()
        project_type = launcher.detect_project_type(str(temp_project))

        assert project_type == "go"

    def test_detect_rust(self, temp_project):
        """Test detecting Rust projects."""
        (temp_project / "Cargo.toml").write_text('[package]\nname = "test"')

        launcher = IDELauncher()
        project_type = launcher.detect_project_type(str(temp_project))

        assert project_type == "rust"

    def test_detect_unknown(self, temp_project):
        """Test detecting unknown project type."""
        launcher = IDELauncher()
        project_type = launcher.detect_project_type(str(temp_project))

        assert project_type == "unknown"


class TestIDEConfigDetection:
    """Tests for existing IDE config detection."""

    def test_detect_vscode(self, temp_project):
        """Test detecting VS Code configuration."""
        (temp_project / ".vscode").mkdir()
        (temp_project / ".vscode" / "settings.json").write_text("{}")

        launcher = IDELauncher()
        ide = launcher.detect_existing_ide_config(str(temp_project))

        assert ide == "code"

    def test_detect_idea_dotnet(self, temp_project):
        """Test detecting JetBrains for .NET project."""
        (temp_project / ".idea").mkdir()
        (temp_project / "MyProject.csproj").write_text("<Project></Project>")

        launcher = IDELauncher()
        ide = launcher.detect_existing_ide_config(str(temp_project))

        assert ide == "rider"

    def test_detect_idea_python(self, temp_project):
        """Test detecting JetBrains for Python project."""
        (temp_project / ".idea").mkdir()
        (temp_project / "pyproject.toml").write_text('[project]\nname = "test"')

        launcher = IDELauncher()
        ide = launcher.detect_existing_ide_config(str(temp_project))

        assert ide == "pycharm"

    def test_detect_idea_nodejs(self, temp_project):
        """Test detecting JetBrains for Node.js project."""
        (temp_project / ".idea").mkdir()
        (temp_project / "package.json").write_text('{"name": "test"}')

        launcher = IDELauncher()
        ide = launcher.detect_existing_ide_config(str(temp_project))

        assert ide == "webstorm"

    def test_detect_idea_java(self, temp_project):
        """Test detecting JetBrains for Java project."""
        (temp_project / ".idea").mkdir()
        (temp_project / "pom.xml").write_text("<project></project>")

        launcher = IDELauncher()
        ide = launcher.detect_existing_ide_config(str(temp_project))

        assert ide == "idea"

    def test_detect_idea_go(self, temp_project):
        """Test detecting JetBrains for Go project."""
        (temp_project / ".idea").mkdir()
        (temp_project / "go.mod").write_text("module test")

        launcher = IDELauncher()
        ide = launcher.detect_existing_ide_config(str(temp_project))

        assert ide == "goland"

    def test_detect_no_config(self, temp_project):
        """Test no IDE config detected."""
        launcher = IDELauncher()
        ide = launcher.detect_existing_ide_config(str(temp_project))

        assert ide is None


class TestBestIDE:
    """Tests for best IDE selection."""

    def test_best_ide_dotnet(self, temp_project):
        """Test best IDE for .NET project."""
        (temp_project / "MyProject.csproj").write_text("<Project></Project>")

        launcher = IDELauncher()
        best = launcher.get_best_ide(str(temp_project))

        # Should be rider if available, otherwise code
        assert best in ["rider", "code"]

    def test_best_ide_python(self, temp_project):
        """Test best IDE for Python project."""
        (temp_project / "pyproject.toml").write_text('[project]\nname = "test"')

        launcher = IDELauncher()
        best = launcher.get_best_ide(str(temp_project))

        # Should be pycharm if available, otherwise code
        assert best in ["pycharm", "code"]

    def test_best_ide_nodejs(self, temp_project):
        """Test best IDE for Node.js project."""
        (temp_project / "package.json").write_text('{"name": "test"}')

        launcher = IDELauncher()
        best = launcher.get_best_ide(str(temp_project))

        # Should be webstorm if available, otherwise code
        assert best in ["webstorm", "code"]

    def test_best_ide_unknown(self, temp_project):
        """Test best IDE for unknown project type."""
        launcher = IDELauncher()
        best = launcher.get_best_ide(str(temp_project))

        # Should default to code
        assert best == "code"


class TestIDEAvailability:
    """Tests for IDE availability checking."""

    def test_check_code_availability(self):
        """Test checking VS Code availability."""
        launcher = IDELauncher()
        # VS Code is commonly available
        result = launcher.is_ide_available("code")
        assert isinstance(result, bool)

    def test_check_unknown_ide(self):
        """Test checking unknown IDE."""
        launcher = IDELauncher()
        result = launcher.is_ide_available("nonexistent-ide")
        assert result is False


class TestListAvailable:
    """Tests for listing available IDEs."""

    def test_list_available(self):
        """Test listing available IDEs."""
        launcher = IDELauncher()
        available = launcher.list_available()

        assert isinstance(available, list)
        # Each item should be a tuple (id, name)
        for item in available:
            assert len(item) == 2
            assert isinstance(item[0], str)
            assert isinstance(item[1], str)
