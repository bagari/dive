import numpy as np
from fury.ui.core import UI, Rectangle2D


class Panel2D(UI):
    """A 2D panel that can contain one or more UI elements.

    Attributes
    ----------
    alignment : str
        Alignment of the panel on screen: ``'left'`` or ``'right'``.
    """

    def __init__(
        self,
        size,
        position=(0, 0),
        color=(0.1, 0.1, 0.1),
        opacity=0.7,
        align='left',
        border_color=(1, 1, 1),
        border_width=0,
        has_border=False,
    ):
        """Init class instance.

        Parameters
        ----------
        size : (int, int)
            Width and height in pixels.
        position : (float, float), optional
            Absolute (x, y) of the lower-left corner.
        color : (float, float, float), optional
            Background color; values in [0, 1].
        opacity : float, optional
            Background opacity; value in [0, 1].
        align : str, optional
            Screen alignment: ``'left'`` (default) or ``'right'``.
        border_color : (float, float, float), optional
            Border color; values in [0, 1].
        border_width : float, optional
            Width of each border in pixels.
        has_border : bool, optional
            Whether to draw borders around the panel.
        """
        self.has_border = has_border
        self._border_color = border_color
        self._border_width = border_width
        super(Panel2D, self).__init__(position=position)
        self.resize(size)
        self.alignment = align
        self.color = color
        self.opacity = opacity
        self.position = position
        self._drag_offset = None

    def _setup(self):
        """Create the background rectangle and optional border rectangles."""
        self._elements = []
        self.element_offsets = []
        self.background = Rectangle2D()

        if self.has_border:
            self.borders = {
                'left':   Rectangle2D(),
                'right':  Rectangle2D(),
                'top':    Rectangle2D(),
                'bottom': Rectangle2D(),
            }
            self.border_coords = {
                'left':   (0.0, 0.0),
                'right':  (1.0, 0.0),
                'top':    (0.0, 1.0),
                'bottom': (0.0, 0.0),
            }
            for key, border in self.borders.items():
                border.color = self._border_color
                self.add_element(border, self.border_coords[key])
                border.on_left_mouse_button_pressed = self.left_button_pressed
                border.on_left_mouse_button_dragged = self.left_button_dragged

        self.add_element(self.background, (0, 0))
        self.background.on_left_mouse_button_pressed = self.left_button_pressed
        self.background.on_left_mouse_button_dragged = self.left_button_dragged

    def _get_actors(self):
        """Get the actors composing this UI component."""
        actors = []
        for element in self._elements:
            actors += element.actors
        return actors

    def _add_to_scene(self, scene):
        """Add all sub-components to the scene.

        Parameters
        ----------
        scene : scene
        """
        for element in self._elements:
            element.add_to_scene(scene)

    def _get_size(self):
        return self.background.size

    def resize(self, size):
        """Resize the panel and its borders.

        Parameters
        ----------
        size : (float, float)
            New width and height in pixels.
        """
        self.background.resize(size)

        if self.has_border:
            self.borders['left'].resize(
                (self._border_width, size[1] + self._border_width))
            self.borders['right'].resize(
                (self._border_width, size[1] + self._border_width))
            self.borders['top'].resize(
                (self.size[0] + self._border_width, self._border_width))
            self.borders['bottom'].resize(
                (self.size[0] + self._border_width, self._border_width))
            self.update_border_coords()

    def _set_position(self, coords):
        """Set the lower-left corner position.

        Parameters
        ----------
        coords : (float, float)
            Absolute pixel coordinates (x, y).
        """
        coords = np.array(coords)
        for element, offset in self.element_offsets:
            element.position = coords + offset

    def set_visibility(self, visibility):
        """Set the visibility of all child elements.

        Parameters
        ----------
        visibility : bool
            ``True`` to show, ``False`` to hide.
        """
        for element in self._elements:
            element.set_visibility(visibility)

    @property
    def color(self):
        """Background color of the panel."""
        return self.background.color

    @color.setter
    def color(self, color):
        self.background.color = color

    @property
    def opacity(self):
        """Background opacity of the panel."""
        return self.background.opacity

    @opacity.setter
    def opacity(self, opacity):
        self.background.opacity = opacity

    def add_element(self, element, coords, anchor='position'):
        """Add a UI element to the panel.

        Coordinates are relative to the panel's lower-left corner.

        Parameters
        ----------
        element : UI
            The element to add.
        coords : (float, float) or (int, int)
            Offset from the panel's lower-left corner.
            Floats are treated as normalized [0, 1] fractions of the panel
            size; ints are treated as absolute pixel offsets.
        anchor : str, optional
            ``'position'`` (default) anchors by lower-left corner;
            ``'center'`` anchors by element center.

        Raises
        ------
        ValueError
            If normalized coords are outside [0, 1] or anchor is unknown.
        """
        coords = np.array(coords)
        if np.issubdtype(coords.dtype, np.floating):
            if np.any(coords < 0) or np.any(coords > 1):
                raise ValueError('Normalized coordinates must be in [0, 1].')
            coords = coords * self.size

        if anchor == 'center':
            element.center = self.position + coords
        elif anchor == 'position':
            element.position = self.position + coords
        else:
            raise ValueError(
                "Unknown anchor '{}'. Supported: 'position', 'center'.".format(anchor))

        self._elements.append(element)
        self.element_offsets.append((element, element.position - self.position))

    def remove_element(self, element):
        """Remove a UI element from the panel.

        Parameters
        ----------
        element : UI
            The element to remove.
        """
        idx = self._elements.index(element)
        del self._elements[idx]
        del self.element_offsets[idx]

    def update_element(self, element, coords, anchor='position'):
        """Reposition a UI element already in the panel.

        Parameters
        ----------
        element : UI
            The element to reposition.
        coords : (float, float) or (int, int)
            New offset from the panel's lower-left corner.
            Floats are normalized [0, 1]; ints are absolute pixels.
        anchor : str, optional
            ``'position'`` (default) or ``'center'``.
        """
        self.remove_element(element)
        self.add_element(element, coords, anchor)

    def update_element_color(self, element, color, coords=(0.001, 0.7), anchor='position'):
        """Update the color of a UI element and re-add it at the given coords.

        Parameters
        ----------
        element : UI
            The element whose color should change.
        color : (float, float, float)
            New color; values in [0, 1].
        coords : (float, float) or (int, int), optional
            Position within the panel (default ``(0.001, 0.7)``).
        anchor : str, optional
            ``'position'`` (default) or ``'center'``.
        """
        self.remove_element(element)
        element.color = color
        self.add_element(element, coords, anchor)

    def left_button_pressed(self, i_ren, _obj, _panel2d_object):
        """Record the drag offset when the panel is clicked.

        Parameters
        ----------
        i_ren : :class:`CustomInteractorStyle`
        _obj : :class:`vtkActor`
        _panel2d_object : :class:`Panel2D`
        """
        self._drag_offset = np.array(i_ren.event.position) - self.position
        i_ren.event.abort()

    def left_button_dragged(self, i_ren, _obj, _panel2d_object):
        """Move the panel to follow the drag.

        Parameters
        ----------
        i_ren : :class:`CustomInteractorStyle`
        _obj : :class:`vtkActor`
        _panel2d_object : :class:`Panel2D`
        """
        if self._drag_offset is not None:
            self.position = np.array(i_ren.event.position) - self._drag_offset
        i_ren.force_render()

    def re_align(self, window_size_change):
        """Adjust the panel position after a window resize.

        Parameters
        ----------
        window_size_change : (int, int)
            Change in window size (delta_width, delta_height) in pixels.

        Raises
        ------
        ValueError
            If alignment is neither ``'left'`` nor ``'right'``.
        """
        if self.alignment == 'left':
            pass
        elif self.alignment == 'right':
            self.position += np.array(window_size_change)
        else:
            raise ValueError(
                'You can only left-align or right-align objects in a panel.')

    def update_border_coords(self):
        """Reposition all border rectangles after a resize."""
        self.border_coords = {
            'left':   (0.0, 0.0),
            'right':  (1.0, 0.0),
            'top':    (0.0, 1.0),
            'bottom': (0.0, 0.0),
        }
        for key, border in self.borders.items():
            self.update_element(border, self.border_coords[key])

    @property
    def border_color(self):
        """Colors of the four borders as a list [left, right, top, bottom]."""
        return [self.borders[side].color for side in ('left', 'right', 'top', 'bottom')]

    @border_color.setter
    def border_color(self, side_color):
        """Set the color of one border.

        Parameters
        ----------
        side_color : (str, tuple)
            A ``(side, color)`` pair where side is one of
            ``'left'``, ``'right'``, ``'top'``, ``'bottom'``.

        Raises
        ------
        ValueError
            If side is not a valid border name.
        """
        side, color = side_color
        if side.lower() not in ('left', 'right', 'top', 'bottom'):
            raise ValueError(f'{side!r} is not a valid border side.')
        self.borders[side].color = color

    @property
    def border_width(self):
        """Widths of the four borders as a list [left, right, top, bottom]."""
        widths = []
        for side in ('left', 'right', 'top', 'bottom'):
            widths.append(
                self.borders[side].width if side in ('left', 'right')
                else self.borders[side].height
            )
        return widths

    @border_width.setter
    def border_width(self, side_width):
        """Set the width of one border.

        Parameters
        ----------
        side_width : (str, float)
            A ``(side, width)`` pair where side is one of
            ``'left'``, ``'right'``, ``'top'``, ``'bottom'``.

        Raises
        ------
        ValueError
            If side is not a valid border name.
        """
        side, width = side_width
        if side.lower() in ('left', 'right'):
            self.borders[side].width = width
        elif side.lower() in ('top', 'bottom'):
            self.borders[side].height = width
        else:
            raise ValueError(f'{side!r} is not a valid border side.')
