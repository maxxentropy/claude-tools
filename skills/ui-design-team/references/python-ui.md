# Python UI Platform Specialist

Implement designs using Python GUI frameworks.

## Framework Selection

| Framework | Strengths | Best For |
|-----------|-----------|----------|
| **PyQt6/PySide6** | Professional-grade, extensive widgets | Complex desktop apps, commercial |
| **Tkinter** | Built-in, no dependencies | Simple tools, quick utilities |
| **wxPython** | Native look per platform | Platform-native appearance |
| **Kivy** | Touch-friendly, mobile | Touch interfaces, mobile apps |
| **Dear PyGui** | GPU-accelerated, immediate mode | Real-time visualization, tools |
| **Streamlit** | Rapid prototyping, reactive | Data dashboards, ML demos |
| **Gradio** | ML model interfaces | Model demos, quick interfaces |

## PyQt6/PySide6 Implementation

### Design Tokens
```python
# design_tokens.py
from dataclasses import dataclass

@dataclass(frozen=True)
class DesignTokens:
    # Colors
    PRIMARY_500: str = "#3B82F6"
    PRIMARY_600: str = "#2563EB"
    NEUTRAL_50: str = "#F9FAFB"
    NEUTRAL_900: str = "#111827"
    
    # Spacing
    SPACING_XS: int = 4
    SPACING_SM: int = 8
    SPACING_MD: int = 16
    SPACING_LG: int = 24
    
    # Typography
    FONT_FAMILY: str = "Segoe UI, sans-serif"
    FONT_SIZE_BASE: int = 14
    
    # Borders
    RADIUS_MD: int = 8

tokens = DesignTokens()
```

### Qt Stylesheet
```python
# styles.py
from design_tokens import tokens

def get_button_stylesheet() -> str:
    return f"""
    QPushButton {{
        background-color: {tokens.PRIMARY_500};
        color: white;
        border: none;
        border-radius: {tokens.RADIUS_MD}px;
        padding: {tokens.SPACING_SM}px {tokens.SPACING_MD}px;
        font-family: {tokens.FONT_FAMILY};
        font-size: {tokens.FONT_SIZE_BASE}px;
        font-weight: 600;
        min-height: 44px;
    }}
    
    QPushButton:hover {{
        background-color: {tokens.PRIMARY_600};
    }}
    
    QPushButton:pressed {{
        background-color: {tokens.PRIMARY_600};
    }}
    
    QPushButton:disabled {{
        background-color: {tokens.NEUTRAL_50};
        color: {tokens.NEUTRAL_900};
        opacity: 0.5;
    }}
    
    QPushButton:focus {{
        outline: 2px solid {tokens.PRIMARY_500};
        outline-offset: 2px;
    }}
    """
```

### Component Pattern
```python
"""
Component: PrimaryButton
Purpose: Main action button with primary styling

Usage:
    button = PrimaryButton("Save", parent)
    button.clicked.connect(handler)

Accessibility:
    - Keyboard: Tab to focus, Enter/Space to activate
    - Screen reader: Accessible name from text
"""

from typing import Optional
from PyQt6.QtWidgets import QPushButton, QWidget
from PyQt6.QtCore import pyqtSignal
from styles import get_button_stylesheet


class PrimaryButton(QPushButton):
    """Primary action button with design system styling."""
    
    def __init__(
        self, 
        text: str, 
        parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(text, parent)
        self._setup_styling()
        self._setup_accessibility()
    
    def _setup_styling(self) -> None:
        self.setStyleSheet(get_button_stylesheet())
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    
    def _setup_accessibility(self) -> None:
        # Accessible name defaults to button text
        # Override with setAccessibleName() if needed
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
```

### Application Structure
```
my_app/
├── __init__.py
├── main.py                 # Entry point
├── app.py                  # QApplication setup
├── design/
│   ├── __init__.py
│   ├── tokens.py           # Design tokens
│   └── styles.py           # Qt stylesheets
├── models/
│   └── ...                 # Business logic (framework-agnostic)
├── views/
│   ├── main_window.py
│   └── components/
│       └── buttons.py
└── controllers/
    └── ...                 # View-model coordination
```

## Tkinter with ttkbootstrap

```python
import ttkbootstrap as ttk
from ttkbootstrap.constants import PRIMARY

def create_app():
    app = ttk.Window(themename="cosmo")
    app.title("My App")
    
    # Custom style
    style = ttk.Style()
    style.configure(
        "Primary.TButton",
        font=("Segoe UI", 10, "bold"),
        padding=(16, 8)
    )
    
    # Button with style
    btn = ttk.Button(
        app,
        text="Click Me",
        style="Primary.TButton",
        bootstyle=PRIMARY
    )
    btn.pack(padx=20, pady=20)
    
    return app
```

## Streamlit (Data Apps)

```python
import streamlit as st

# Page config
st.set_page_config(
    page_title="My App",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .stButton > button {
        background-color: #3B82F6;
        color: white;
        border-radius: 8px;
        padding: 8px 16px;
        font-weight: 600;
    }
    .stButton > button:hover {
        background-color: #2563EB;
    }
</style>
""", unsafe_allow_html=True)

# Components
st.title("Dashboard")

col1, col2 = st.columns(2)
with col1:
    if st.button("Action"):
        st.success("Done!")
```

## Accessibility Considerations

### PyQt6
```python
# Accessible name
button.setAccessibleName("Submit form")
button.setAccessibleDescription("Saves your changes")

# Keyboard shortcuts
from PyQt6.QtGui import QShortcut, QKeySequence
shortcut = QShortcut(QKeySequence("Ctrl+S"), window)
shortcut.activated.connect(save_handler)

# Tab order
widget1.setTabOrder(widget1, widget2)
```

### Focus Management
```python
# Set initial focus
widget.setFocus()

# Focus policy
widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # Tab + click
widget.setFocusPolicy(Qt.FocusPolicy.TabFocus)     # Tab only
```

## Cross-Platform Considerations
- Test on Windows, macOS, Linux
- Use system fonts with fallbacks
- Handle high-DPI displays
- Respect OS dark mode when possible

## Output Standards

1. Type hints on all functions and methods
2. Docstrings for modules, classes, public methods
3. Design tokens in dedicated module (not hardcoded)
4. MVC/MVP separation (testable business logic)
5. Accessibility (keyboard navigation, screen reader support)
6. All states implemented (normal, hover, pressed, disabled, focused)
7. PEP 8 compliant style
