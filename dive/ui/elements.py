import numpy as np
from fury import ui
from numbers import Number
from importlib.resources import files
from collections import OrderedDict
from fury.data import read_viz_icons
from fury.ui.core import UI, Button2D, Disk2D, Rectangle2D, TextBlock2D

import dive.ui as _ui


_ASSETS = files("dive").joinpath("assets")
_ICON_ADD = str(_ASSETS.joinpath("add.png"))
_ICON_MINUS = str(_ASSETS.joinpath("minus.png"))


class ComboBox2D(UI):
    """A drop-down menu UI element.

    Attributes
    ----------
    selection_box : :class:`TextBlock2D`
        Displays the current selection and placeholder text.
    drop_down_button : :class:`Button2D`
        Toggles the drop-down menu visibility.
    drop_down_menu : :class:`ListBox2D`
        The list of selectable items.
    """

    def __init__(
        self,
        items=[],
        position=(0, 0),
        size=(150, 400),
        placeholder='Choose selection...',
        draggable=False,
        selection_text_color=(0, 0, 0),
        selection_bg_color=(0.9, 0.9, 0.9),
        menu_text_color=(0.2, 0.2, 0.2),
        selected_color=(0.6, 0.6, 0.9),
        unselected_color=(0.6, 0.6, 0.6),
        scroll_bar_active_color=(0.2, 0.2, 0.6),
        scroll_bar_inactive_color=(0.0, 0.0, 0.9),
        menu_opacity=1.0,
        reverse_scrolling=True,
        font_size=20,
        line_spacing=1.0,
        others=[],
    ):
        """Init class Instance.

        Parameters
        ----------
        items: list(string)
            List of items to be displayed as choices.
        position : (float, float)
            Absolute coordinates (x, y) of the lower-left corner of this
            UI component.
        size : (int, int)
            Width and height in pixels of this UI component.
        placeholder : str
            Holds the default text to be displayed.
        draggable: {True, False}
            Whether the UI element is draggable or not.
        selection_text_color : tuple of 3 floats
            Color of the selected text to be displayed.
        selection_bg_color : tuple of 3 floats
            Background color of the selection text.
        menu_text_color : tuple of 3 floats.
            Color of the options displayed in drop down menu.
        selected_color : tuple of 3 floats.
            Background color of the selected option in drop down menu.
        unselected_color : tuple of 3 floats.
            Background color of the unselected option in drop down menu.
        scroll_bar_active_color : tuple of 3 floats.
            Color of the scrollbar when in active use.
        scroll_bar_inactive_color : tuple of 3 floats.
            Color of the scrollbar when inactive.
        reverse_scrolling: {True, False}
            If True, scrolling up will move the list of files down.
        font_size: int
            The font size of selected text in pixels.
        line_spacing: float
            Distance between drop down menu's items in pixels.
        """
        items = list(items or [])
        others = list(others or [])
        self.items = items.copy()
        self.font_size = font_size
        self.reverse_scrolling = reverse_scrolling
        self.line_spacing = line_spacing
        self.panel_size = size
        self._selection = placeholder
        self.main_placeholder = placeholder
        self._menu_visibility = False
        self._selection_ID = None
        self.draggable = draggable
        self.sel_text_color = selection_text_color
        self.sel_bg_color = selection_bg_color
        self.menu_txt_color = menu_text_color
        self.selected_color = selected_color
        self.unselected_color = unselected_color
        self.scroll_active_color = scroll_bar_active_color
        self.scroll_inactive_color = scroll_bar_inactive_color
        self.menu_opacity = menu_opacity
        self.others = others
        self.on_change = lambda combobox: None
        self.text_block_size = (int(size[0]), int(size[1]))
        self.drop_menu_size = (int(0.9 * size[0]), int(0.7 * size[1]))
        self.drop_button_size = (int(0.08 * size[0]), int(0.14 * size[1]))

        self._icon_files = [
            ('left',  read_viz_icons(fname=_ICON_ADD)),
            ('down',  read_viz_icons(fname=_ICON_MINUS))
        ]

        super(ComboBox2D, self).__init__()
        self.position = position

    def _setup(self):
        """Setup this UI component.

        Create the ListBox filled with empty slots (ListBoxItem2D).
        Create TextBox with placeholder text.
        Create Button for toggling drop down menu.
        """
        self.selection_box = TextBlock2D(
            size=(20, 20),
            color=self.sel_text_color,
            text=self._selection,
        )

        self.drop_down_button = Button2D(
            icon_fnames=self._icon_files, size=self.drop_button_size
        )

        self.drop_down_menu = ui.ListBox2D(
            values=self.items,
            multiselection=False,
            font_size=self.font_size,
            line_spacing=self.line_spacing,
            text_color=self.menu_txt_color,
            selected_color=self.selected_color,
            unselected_color=self.unselected_color,
            scroll_bar_active_color=self.scroll_active_color,
            scroll_bar_inactive_color=self.scroll_inactive_color,
            background_opacity=self.menu_opacity,
            reverse_scrolling=self.reverse_scrolling,
            size=self.drop_menu_size,
        )

        self.drop_down_menu.set_visibility(False)

        self.panel = ui.Panel2D(self.panel_size, opacity=0.0)
        self.panel.add_element(self.selection_box, (0.001, 0.7))
        self.panel.add_element(self.drop_down_button, (0.8, 0.7))
        self.panel.add_element(self.drop_down_menu, (0, 0))

        self.panel.background.on_left_mouse_button_dragged = (
            lambda i_ren, _obj, _comp: i_ren.force_render
        )
        self.drop_down_menu.panel.background.on_left_mouse_button_dragged = (
            lambda i_ren, _obj, _comp: i_ren.force_render
        )

        for slot in self.drop_down_menu.slots:
            slot.add_callback(slot.textblock.actor, 'LeftButtonPressEvent', self.select_option_callback)
            slot.add_callback(slot.background.actor, 'LeftButtonPressEvent', self.select_option_callback)

        self.drop_down_button.on_left_mouse_button_clicked = self.menu_toggle_callback
        self.on_change = lambda ui: None

    def _get_actors(self):
        """Get the actors composing this UI component."""
        return self.panel.actors

    def _handle_option_change(self):
        """Update whenever an option changes.

        Parameters
        ----------
        option : :class:`Option`
        """
        self.selection_box.bold = self.drop_down_button.current_icon_id == 1
        self.on_change(self)

    def resize(self, size):
        """Resize ComboBox2D.

        Parameters
        ----------
        size : (int, int)
            ComboBox size(width, height) in pixels.
        """
        self.panel.resize(size)
        self.drop_menu_size = (size[0], int(0.7 * size[1]))
        self.drop_button_size = (int(0.2 * size[0]), int(0.3 * size[1]))
        self.panel.update_element(self.selection_box, (0.001, 0.7))
        self.panel.update_element(self.drop_down_button, (0.8, 0.7))
        self.panel.update_element(self.drop_down_menu, (0, 0))
        self.drop_down_button.resize(self.drop_button_size)
        self.drop_down_menu.resize(self.drop_menu_size)

    def _set_position(self, coords):
        """Set the lower-left corner position.

        Parameters
        ----------
        coords : (float, float)
            Absolute pixel coordinates (x, y).
        """
        self.panel.position = coords

    def _add_to_scene(self, scene):
        """Add this UI component to the scene.

        Parameters
        ----------
        scene : scene
        """
        self.panel.add_to_scene(scene)
        self.selection_box.font_size = self.font_size

    def _get_size(self):
        return self.panel.size

    @property
    def selected_text(self):
        """Return the currently selected text."""
        return self._selection

    @property
    def selected_text_index(self):
        """Return the index of the currently selected item."""
        return self._selection_ID

    def set_visibility(self, visibility):
        """Set visibility, keeping drop-down hidden when closed."""
        super().set_visibility(visibility)
        if not self._menu_visibility:
            self.drop_down_menu.set_visibility(False)

    def append_item(self, *items):
        """Append additional options to the menu.

        Parameters
        ----------
        items : str, Number, list, or tuple
            One or more items to add.
        """
        for item in items:
            if isinstance(item, (list, tuple)):
                self.append_item(*item)
            elif isinstance(item, (str, Number)):
                self.items.append(str(item))
            else:
                raise TypeError('Invalid item instance {}'.format(type(item)))

        self.drop_down_menu.update()
        self.resize(self.panel_size)
        self.drop_down_menu.set_visibility(False)
        if not self._menu_visibility:
            self.drop_down_menu.scroll_bar.set_visibility(False)

    def remove_item(self, string_to_remove):
        """Remove all occurrences of an item from the menu.

        Parameters
        ----------
        string_to_remove : str
            The item label to remove.
        """
        while string_to_remove in self.items:
            self.items.remove(string_to_remove)
            self.drop_down_menu.update()
            self.resize(self.panel_size)
            self._selection = self.main_placeholder
            self.selection_box.message = self._selection
            self._selection_ID = None
            self.drop_down_menu.set_visibility(False)

    def select_option_callback(self, i_ren, _obj, listboxitem):
        """Handle item selection from the drop-down list.

        Parameters
        ----------
        i_ren : :class:`CustomInteractorStyle`
        _obj : :class:`vtkActor`
        listboxitem : :class:`ListBoxItem2D`
        """
        _ui.selected_item = listboxitem.element
        truncated = (listboxitem.element[:15]
                     if len(listboxitem.element) > 15 else listboxitem.element)
        self._selection = self.main_placeholder + truncated
        self._selection_ID = self.items.index(listboxitem.element)
        self.selection_box.message = self._selection
        self.drop_down_menu.set_visibility(False)
        self._menu_visibility = False

        self.drop_down_button.next_icon()
        visible = self.drop_down_button.current_icon_id != 1
        for other in self.others:
            other.set_visibility(visible)

        self.on_change(self)
        i_ren.force_render()
        i_ren.event.abort()

    def menu_toggle_callback(self, i_ren, _vtkactor, _combobox):
        """Toggle the drop-down menu visibility.

        Parameters
        ----------
        i_ren : :class:`CustomInteractorStyle`
        _vtkactor : :class:`vtkActor`
        _combobox : :class:`ComboBox2D`
        """
        self._menu_visibility = not self._menu_visibility
        self.drop_down_menu.set_visibility(self._menu_visibility)
        self.drop_down_button.next_icon()
        visible = self.drop_down_button.current_icon_id != 1
        for other in self.others:
            other.set_visibility(visible)
            if not visible and isinstance(other, ComboBox2D):
                other.selection_box.bold = False
        i_ren.force_render()
        i_ren.event.abort()

    def left_button_pressed(self, i_ren, _obj, _sub_component):
        """Record click position for dragging."""
        self._click_position = np.array(i_ren.event.position)
        i_ren.event.abort()

    def left_button_dragged(self, i_ren, _obj, _sub_component):
        """Move the panel by the drag delta."""
        click_position = np.array(i_ren.event.position)
        self.panel.position += click_position - self._click_position
        self._click_position = click_position
        i_ren.force_render()


class Option(UI):
    """A set of a Button2D and a TextBlock2D to act as a single option
    for checkboxes and radio buttons.
    Clicking the button toggles its checked/unchecked status.

    Attributes
    ----------
    label : str
        The label for the option.
    font_size : int
            Font Size of the label.
    checked : bool
        Current checked state of the option.
    """

    def __init__(self, label, position=(0, 0), font_size=18, checked=False, icon=None):
        """Init this class instance.

        Parameters
        ----------
        label : str
            Text displayed next to the button.
        position : (float, float)
            Absolute (x, y) of the lower-left corner of the button.
        font_size : int
            Font size of the label.
        checked : bool, optional
            Initial checked state.
        icon : str or None, optional
            Full path to a custom icon image.  When supplied the same
            image is used for both checked and unchecked states.
            When ``None`` (default) FURY's built-in stop/checkmark
            icons are used.
        """
        self.label = label
        self.font_size = font_size
        self.checked = checked
        self._icon = icon
        self.button_size = (font_size * 1.2, font_size * 1.2)
        self.button_label_gap = 10
        super(Option, self).__init__(position=position)
        self.on_change = lambda obj: None

    def _setup(self):
        """Set up the button and label sub-components."""
        if self._icon is not None:
            icon_img = read_viz_icons(fname=self._icon)
            icons = [('unchecked', icon_img), ('checked', icon_img)]
        else:
            icons = [
                ('unchecked', read_viz_icons(fname='stop2.png')),
                ('checked',   read_viz_icons(fname='checkmark.png')),
            ]

        self.button = Button2D(icon_fnames=icons, size=self.button_size)
        self.text = TextBlock2D(text=self.label, font_size=self.font_size, color=(0, 0, 0))

        if self.checked:
            self.button.set_icon_by_name('checked')

        self.button.on_left_mouse_button_clicked = self.toggle
        self.text.on_left_mouse_button_clicked = self.toggle

    def _get_actors(self):
        """Get the actors composing this UI component."""
        return self.button.actors + self.text.actors

    def _add_to_scene(self, scene):
        """Add all sub-components to the scene.

        Parameters
        ----------
        scene : scene
        """
        self.button.add_to_scene(scene)
        self.text.add_to_scene(scene)

    def _get_size(self):
        width = self.button.size[0] + self.button_label_gap + self.text.size[0]
        height = max(self.button.size[1], self.text.size[1])
        return np.array([width, height])

    def _set_position(self, coords):
        """Set the lower-left corner position.

        Parameters
        ----------
        coords : (float, float)
            Absolute pixel coordinates (x, y).
        """
        num_newlines = self.label.count('\n')
        self.button.position = coords + (0, num_newlines * self.font_size * 0.5)
        offset = (self.button.size[0] + self.button_label_gap, 0)
        self.text.position = coords + offset

    def toggle(self, i_ren, _obj, _element):
        """Toggle the checked state and fire on_change."""
        if self.checked:
            self.deselect()
        else:
            self.select()
        self.on_change(self)
        i_ren.force_render()

    def select(self):
        """Mark this option as checked."""
        self.checked = True
        self.button.set_icon_by_name('checked')

    def deselect(self):
        """Mark this option as unchecked."""
        self.checked = False
        self.button.set_icon_by_name('unchecked')


class Checkbox(UI):
    """A 2D set of :class:'Option' objects.
    Multiple options can be selected.

    Attributes
    ----------
    labels : list(string)
        List of labels of each option.
    options : dict(Option)
        Dictionary of all the options in the checkbox set.
    padding : float
        Distance between two adjacent options
    """

    def __init__(
        self,
        labels,
        checked_labels=(),
        padding=1,
        font_size=18,
        font_family='Arial',
        position=(0, 0),
    ):
        """Init this class instance.
        Parameters
        ----------
        labels : list(str)
            List of labels of each option.
        checked_labels: list(str), optional
            List of labels that are checked on setting up.
        padding : float, optional
            The distance between two adjacent options
        font_size : int, optional
            Size of the text font.
        font_family : str, optional
            Currently only supports Arial.
        position : (float, float), optional
            Absolute coordinates (x, y) of the lower-left corner of
            the button of the first option.
        """
        self.labels = list(reversed(list(labels)))
        self._padding = padding
        self._font_size = font_size
        self.font_family = font_family
        self.checked_labels = list(checked_labels)
        super(Checkbox, self).__init__(position=position)
        self.on_change = lambda checkbox: None

    def _setup(self):
        """Setup this UI component."""
        self.options = OrderedDict()
        button_y = self.position[1]
        for label in self.labels:
            option = Option(
                label=label,
                font_size=self.font_size,
                position=(self.position[0], button_y),
                checked=(label in self.checked_labels),
            )
            line_spacing = option.text.actor.GetTextProperty().GetLineSpacing()
            button_y = (
                button_y
                + self.font_size * (label.count('\n') + 1) * (line_spacing + 0.1)
                + self.padding
            )
            self.options[label] = option
            option.on_change = self._handle_option_change

    def _get_actors(self):
        """Get the actors composing this UI component."""
        actors = []
        for option in self.options.values():
            actors += option.actors
        return actors

    def _add_to_scene(self, scene):
        """Add all subcomponents or VTK props that compose this UI component.

        Parameters
        ----------
        scene : scene
        """
        for option in self.options.values():
            option.add_to_scene(scene)

    def _get_size(self):
        option_width, option_height = self.options.values()[0].get_size()
        height = len(self.labels) * (option_height + self.padding) - self.padding
        return np.asarray([option_width, height])

    def _handle_option_change(self, option):
        """Update checked_labels when an option changes.

        Parameters
        ----------
        option : :class:`Option`
        """
        if option.checked:
            self.checked_labels.append(option.label)
        else:
            self.checked_labels.remove(option.label)
        self.on_change(self)

    def _set_position(self, coords):
        """Set the lower-left corner position.

        Parameters
        ----------
        coords : (float, float)
            Absolute pixel coordinates (x, y).
        """
        button_y = coords[1]
        for option_no, option in enumerate(self.options.values()):
            option.position = (coords[0], button_y)
            line_spacing = option.text.actor.GetTextProperty().GetLineSpacing()
            button_y = (
                button_y
                + self.font_size
                * (self.labels[option_no].count('\n') + 1)
                * (line_spacing + 0.1)
                + self.padding
            )

    @property
    def font_size(self):
        """Font size of the option labels."""
        return self._font_size

    @property
    def padding(self):
        """Pixel gap between adjacent options."""
        return self._padding


class RadioButton(Checkbox):
    """A set of :class:`Option` objects where only one can be selected.

    Attributes
    ----------
    labels : list of str
        Labels for each option.
    options : dict of str -> :class:`Option`
        All options keyed by label.
    padding : float
        Pixel gap between adjacent options.
    """

    def __init__(
        self,
        labels,
        checked_labels,
        padding=1,
        font_size=18,
        font_family='Arial',
        position=(0, 0),
    ):
        """Init this class instance.

        Parameters
        ----------
        labels : list of str
            Labels for each option.
        checked_labels : list of str
            The single label that starts checked (must have length ≤ 1).
        padding : float, optional
            Pixel gap between adjacent options.
        font_size : int, optional
            Font size for all option labels.
        font_family : str, optional
            Font family (currently only 'Arial' is supported).
        position : (float, float), optional
            Absolute (x, y) of the lower-left corner of the first option.

        Raises
        ------
        ValueError
            If more than one label is pre-selected.
        """
        if len(checked_labels) > 1:
            raise ValueError('Only one option can be pre-selected for radio buttons.')
        super(RadioButton, self).__init__(
            labels=labels,
            position=position,
            padding=padding,
            font_size=font_size,
            font_family=font_family,
            checked_labels=checked_labels,
        )

    def _handle_option_change(self, option):
        """Deselect all options, then select only the chosen one."""
        for opt in self.options.values():
            opt.deselect()
        option.select()
        self.checked_labels = [option.label]
        self.on_change(self)


class LineSlider2D(UI):
    """A 2D line slider with a draggable handle and a value label.

    Attributes
    ----------
    line_width : int
        Width of the track line.
    length : int
        Length of the slider.
    track : :class:`Rectangle2D`
        The line the handle slides along.
    handle : :class:`Disk2D` or :class:`Rectangle2D`
        The draggable handle.
    text : :class:`TextBlock2D`
        Displays the current value.
    shape : str
        Shape of the handle: ``'disk'`` or ``'square'``.
    default_color : (float, float, float)
        Handle color when not pressed.
    active_color : (float, float, float)
        Handle color when pressed.
    """

    def __init__(
        self,
        center=(0, 0),
        initial_value=50,
        min_value=0,
        max_value=100,
        length=200,
        line_width=5,
        inner_radius=0,
        outer_radius=10,
        handle_side=20,
        font_size=16,
        orientation='horizontal',
        text_alignment='',
        text_template='{value:.1f} ({ratio:.0%})',
        shape='disk',
    ):
        """Init this UI element.

        Parameters
        ----------
        center : (float, float)
            Center of the slider.
        initial_value : float
            Starting value.
        min_value : float
            Minimum value.
        max_value : float
            Maximum value.
        length : int
            Length of the track in pixels.
        line_width : int
            Width of the track in pixels.
        inner_radius : int
            Inner radius of the handle (disk shape only).
        outer_radius : int
            Outer radius of the handle (disk shape only).
        handle_side : int
            Side length of the handle (square shape only).
        font_size : int
            Font size of the value label.
        orientation : str
            ``'horizontal'`` or ``'vertical'``.
        text_alignment : str
            For horizontal: ``'top'`` or ``'bottom'`` (default).
            For vertical: ``'left'`` (default) or ``'right'``.
        text_template : str or callable
            Format string with ``{value:}`` and/or ``{ratio:}``
            placeholders, or a callable that receives this instance.
        shape : str
            Handle shape: ``'disk'`` (default) or ``'square'``.
        """
        self.shape = shape
        self.orientation = orientation.lower().strip()
        self.align_dict = {
            'horizontal': ['top', 'bottom'],
            'vertical': ['left', 'right'],
        }
        self.default_color = (0, 0, 0)
        self.active_color = (0, 0, 1)
        self.alignment = text_alignment.lower()
        super(LineSlider2D, self).__init__()

        if self.orientation == 'horizontal':
            self.alignment = 'bottom' if not self.alignment else self.alignment
            self.track.width = length
            self.track.height = line_width
        elif self.orientation == 'vertical':
            self.alignment = 'left' if not self.alignment else self.alignment
            self.track.width = line_width
            self.track.height = length
        else:
            raise ValueError('Unknown orientation')

        if self.alignment not in self.align_dict[self.orientation]:
            raise ValueError(
                "Unknown alignment: choose from '{}' or '{}'".format(
                    *self.align_dict[self.orientation]
                )
            )

        if shape == 'disk':
            self.handle.inner_radius = inner_radius
            self.handle.outer_radius = outer_radius
        elif shape == 'square':
            self.handle.width = handle_side
            self.handle.height = handle_side

        self.center = center
        self.min_value = min_value
        self.max_value = max_value
        self.text.font_size = font_size
        self.text_template = text_template

        self.on_change = lambda ui: None
        self.on_value_changed = lambda ui: None
        self.on_moving_slider = lambda ui: None

        self.value = initial_value
        self.update()

    def _setup(self):
        """Create the track, handle, and text sub-components."""
        self.track = Rectangle2D()
        self.track.color = (0, 0, 1)

        if self.shape == 'disk':
            self.handle = Disk2D(outer_radius=1)
        elif self.shape == 'square':
            self.handle = Rectangle2D(size=(1, 1))
        self.handle.color = self.default_color

        self.text = TextBlock2D(justification='center', vertical_justification='top', color=(0, 0, 0))

        self.track.on_left_mouse_button_pressed = self.track_click_callback
        self.track.on_left_mouse_button_dragged = self.handle_move_callback
        self.track.on_left_mouse_button_released = self.handle_release_callback
        self.handle.on_left_mouse_button_dragged = self.handle_move_callback
        self.handle.on_left_mouse_button_released = self.handle_release_callback

    def _get_actors(self):
        """Get the actors composing this UI component."""
        return self.track.actors + self.handle.actors + self.text.actors

    def _add_to_scene(self, scene):
        """Add all sub-components to the scene.

        Parameters
        ----------
        scene : scene
        """
        self.track.add_to_scene(scene)
        self.handle.add_to_scene(scene)
        self.text.add_to_scene(scene)

    def _get_size(self):
        if self.orientation == 'horizontal':
            width = self.track.width + self.handle.size[0]
            height = max(self.track.height, self.handle.size[1])
        else:
            width = max(self.track.width, self.handle.size[0])
            height = self.track.height + self.handle.size[1]
        return np.array([width, height])

    def _set_position(self, coords):
        """Set the lower-left corner position.

        Parameters
        ----------
        coords : (float, float)
            Absolute pixel coordinates (x, y).
        """
        track_position = coords + self.handle.size / 2.0
        if self.orientation == 'horizontal':
            track_position[1] -= self.track.size[1] / 2.0
        else:
            track_position[0] += self.track.size[0] / 2.0

        self.track.position = track_position
        self.handle.position = self.handle.position.astype(float)
        self.handle.position += coords - self.position

        if self.orientation == 'horizontal':
            align = 35 if self.alignment == 'top' else -10
            self.text.position = (self.handle.center[0],
                                  self.handle.position[1] + align)
        else:
            align = 70 if self.alignment == 'right' else -35
            self.text.position = (self.handle.position[0] + align,
                                  self.handle.center[1] + 2)

    @property
    def bottom_y_position(self):
        """Bottom Y position of the track."""
        return self.track.position[1]

    @property
    def top_y_position(self):
        """Top Y position of the track."""
        return self.track.position[1] + self.track.size[1]

    @property
    def left_x_position(self):
        """Left X position of the track."""
        return self.track.position[0]

    @property
    def right_x_position(self):
        """Right X position of the track."""
        return self.track.position[0] + self.track.size[0]

    def set_position(self, position):
        """Move the handle to the given position, clamped to the track.

        Parameters
        ----------
        position : (float, float)
            Target absolute position (x, y).
        """
        if self.orientation == 'horizontal':
            x = max(self.left_x_position, min(position[0], self.right_x_position))
            self.handle.center = (x, self.track.center[1])
        else:
            y = max(self.bottom_y_position, min(position[1], self.top_y_position))
            self.handle.center = (self.track.center[0], y)
        self.update()

    @property
    def value(self):
        """Current slider value."""
        return self._value

    @value.setter
    def value(self, value):
        value_range = self.max_value - self.min_value
        self.ratio = (value - self.min_value) / value_range if value_range else 0
        self.on_value_changed(self)

    @property
    def ratio(self):
        """Current slider position as a fraction [0, 1]."""
        return self._ratio

    @ratio.setter
    def ratio(self, ratio):
        position_x = self.left_x_position + ratio * self.track.width
        position_y = self.bottom_y_position + ratio * self.track.height
        self.set_position((position_x, position_y))

    def format_text(self):
        """Return the formatted value string for the label."""
        if callable(self.text_template):
            return self.text_template(self)
        return self.text_template.format(ratio=self.ratio, value=self.value)

    def update(self):
        """Recompute ratio, value, and label text from handle position."""
        if self.orientation == 'horizontal':
            length = float(self.right_x_position - self.left_x_position)
            length = np.round(length, decimals=6)
            if length != self.track.width:
                raise ValueError('Disk position outside the slider line')
            disk_pos = self.handle.center[0]
            self._ratio = (disk_pos - self.left_x_position) / length
        else:
            length = float(self.top_y_position - self.bottom_y_position)
            if length != self.track.height:
                raise ValueError('Disk position outside the slider line')
            disk_pos = self.handle.center[1]
            self._ratio = (disk_pos - self.bottom_y_position) / length

        value_range = self.max_value - self.min_value
        self._value = self.min_value + self.ratio * value_range
        self.text.message = self.format_text()

        if self.orientation == 'horizontal':
            self.text.position = (disk_pos, self.text.position[1])
        else:
            self.text.position = (self.text.position[0], disk_pos)

        self.on_change(self)

    def track_click_callback(self, i_ren, _vtkactor, _slider):
        """Move handle to click position and grab focus.

        Parameters
        ----------
        i_ren : :class:`CustomInteractorStyle`
        _vtkactor : :class:`vtkActor`
        _slider : :class:`LineSlider2D`
        """
        self.set_position(i_ren.event.position)
        self.on_moving_slider(self)
        i_ren.force_render()
        i_ren.event.abort()

    def handle_move_callback(self, i_ren, _vtkactor, _slider):
        """Move handle while dragging.

        Parameters
        ----------
        i_ren : :class:`CustomInteractorStyle`
        _vtkactor : :class:`vtkActor`
        _slider : :class:`LineSlider2D`
        """
        self.handle.color = self.active_color
        self.set_position(i_ren.event.position)
        self.on_moving_slider(self)
        i_ren.force_render()
        i_ren.event.abort()

    def handle_release_callback(self, i_ren, _vtkactor, _slider):
        """Restore default handle color on release.

        Parameters
        ----------
        i_ren : :class:`CustomInteractorStyle`
        _vtkactor : :class:`vtkActor`
        _slider : :class:`LineSlider2D`
        """
        self.handle.color = self.default_color
        i_ren.force_render()

