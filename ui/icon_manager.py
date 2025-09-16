import qtawesome as qta
from PyQt6.QtCore import QObject
from PyQt6.QtGui import QIcon


class IconManager(QObject):
    """Manages QtAwesome icons with dynamic theme support"""

    def __init__(self, theme_manager):
        super().__init__()
        self.theme_manager = theme_manager

        # Store icon definitions for regeneration
        self.icon_registry = {}  # widget_id -> icon_definition
        self.tracked_widgets = []  # List of widgets with icons

    def create_icon(self, icon_name: str, **kwargs) -> QIcon:
        """Create a themed QtAwesome icon"""
        palette = self.theme_manager.get_palette()

        # Default colors if not provided
        icon_kwargs = {
            "color": palette.COLOR_TEXT_1,
            "color_active": palette.COLOR_TEXT_1,
            "color_disabled": palette.COLOR_DISABLED,
            **kwargs,  # Allow override of default colors
        }

        return qta.icon(icon_name, **icon_kwargs)

    def register_widget_icon(self, widget, icon_name: str, **kwargs):
        """Register a widget's icon for automatic updates"""
        widget_id = id(widget)

        # Store the icon definition
        self.icon_registry[widget_id] = {
            "icon_name": icon_name,
            "kwargs": kwargs,
            "widget": widget,
        }

        # Track the widget
        if widget not in self.tracked_widgets:
            self.tracked_widgets.append(widget)

        # Set initial icon
        icon = self.create_icon(icon_name, **kwargs)
        widget.setIcon(icon)

    def update_all_icons(self):
        """Update all registered icons with new theme colors"""
        # Clean up dead widget references
        self.tracked_widgets = [
            w
            for w in self.tracked_widgets
            if not (hasattr(w, "isDeleted") and w.isDeleted())
        ]

        # Update each registered widget
        for (
            widget
        ) in self.tracked_widgets.copy():  # Copy to avoid modification during iteration
            try:
                widget_id = id(widget)
                if widget_id in self.icon_registry:
                    icon_def = self.icon_registry[widget_id]
                    new_icon = self.create_icon(
                        icon_def["icon_name"], **icon_def["kwargs"]
                    )
                    widget.setIcon(new_icon)
            except RuntimeError:
                # Widget has been deleted
                self.tracked_widgets.remove(widget)
                if widget_id in self.icon_registry:
                    del self.icon_registry[widget_id]
