"""
Reading ICD-Files
"""
# Copyright (C) 2009-2013 Thomas Aglassinger
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License
# for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import inspect
import logging

from cutplace import data
from cutplace import fields
from cutplace import errors
from cutplace import checks
from cutplace import _tools

_log = logging.getLogger("cutplace")


class Cid():
    _EMPTY_INDICATOR = "x"
    _ID_CHECK = "c"
    _ID_DATA_FORMAT = "d"
    _ID_FIELD_RULE = "f"
    _VALID_IDS = [_ID_CHECK, _ID_DATA_FORMAT, _ID_FIELD_RULE]

    def __init__(self):
        self._data_format = None
        self._field_names = []
        self._field_formats = []
        self._field_name_to_format_map = {}
        self._field_name_to_index_map = {}
        self._check_names = []
        self._check_name_to_check_map = {}
        self._validation_listeners = []
        self._reset_counts()
        self._location = None
        self._check_name_to_class_map = self._create_name_to_class_map(checks.AbstractCheck)
        self._field_format_name_to_class_map = self._create_name_to_class_map(fields.AbstractFieldFormat)

    @property
    def data_format(self):
        """
        The data format used by the this ICD; refer to the `data` module for possible formats.
        """
        return self._data_format

    @property
    def field_names(self):
        """List of field names defined in this ICD in the order they have been defined."""
        return self._field_names

    @property
    def field_formats(self):
        """List of field names defined in this ICD in the order they have been defined."""
        return self._field_formats

    @property
    def check_names(self):
        """List of check names in no particular order."""
        return self._check_names

    @property
    def check_map(self):
        """List of check names in no particular order."""
        return self._check_name_to_check_map

    def _reset_counts(self):
        self.accepted_count = 0
        self.rejected_count = 0
        self.failed_checks_at_end_count = 0
        self.passed_checks_at_end_count = 0

    def _class_info(self, some_class):
        assert some_class is not None
        qualified_name = some_class.__module__ + "." + some_class.__name__
        try:
            source_path = inspect.getsourcefile(some_class)
        except TypeError:
            source_path = "(internal)"
        result = qualified_name + " (see: \"" + source_path + "\")"
        return result

    def _create_name_to_class_map(self, base_class):
        assert base_class is not None
        result = {}
        # Note: we use a ``set`` of sub classes to ignore duplicates.
        for class_to_process in set(base_class.__subclasses__()):
            qualified_class_name = class_to_process.__name__
            plain_class_name = qualified_class_name.split('.')[-1]
            clashing_class = result.get(plain_class_name)
            if clashing_class is not None:
                clashing_class_info = self._class_info(clashing_class)
                class_to_process_info = self._class_info(class_to_process)
                if clashing_class_info == class_to_process_info:
                    # HACK: Ignore duplicate class.es Such classes can occur after `importPlugins`
                    # has been called more than once.
                    class_to_process = None
                else:
                    raise errors.CutplaceError("clashing plugin class names must be resolved: %s and %s"
                                               % (clashing_class_info, class_to_process_info))
            if class_to_process is not None:
                result[plain_class_name] = class_to_process
        return result

    def _create_class(self, name_to_class_map, class_qualifier, class_name_appendix, type_name,
                      error_to_raise_on_unknown_class):
        assert name_to_class_map
        assert class_qualifier
        assert class_name_appendix
        assert type_name
        assert error_to_raise_on_unknown_class is not None
        class_name = class_qualifier.split(".")[-1] + class_name_appendix
        result = name_to_class_map.get(class_name)
        if result is None:
            raise error_to_raise_on_unknown_class("cannot find class for %s %s: related class is %s but must be one of: %s"
                                                  % (type_name, class_qualifier, class_name,
                                                     _tools.humanReadableList(sorted(name_to_class_map.keys()))))
        return result

    def _create_field_format_class(self, field_type):
        assert field_type
        return self._create_class(self._field_format_name_to_class_map, field_type, "FieldFormat", "field",
                                  errors.FieldSyntaxError)

    def _create_check_class(self, check_type):
        assert check_type
        return self._create_class(self._check_name_to_class_map, check_type, "Check", "check", errors.CheckSyntaxError)

    def read(self, source_path, rows):
        # TODO: Detect format and use proper reader.
        self._location = errors.InputLocation(source_path, has_cell=True)
        # local_interface = interface.self()
        for row in rows:
            if row:
                row_type = row[0].lower()
                row_data = (row[1:] + [''] * 6)[:6]
                if row_type == 'd':
                    name, value = row_data[:2]
                    self._location.advance_cell()
                    if name == '':
                        raise errors.DataFormatSyntaxError('name of data format property must be specified', self._location)
                    self._location.advance_cell()
                    if self._data_format is None:
                        self._data_format = data.DataFormat(value.lower(), self._location)
                    else:
                        self._data_format.set_property(name.lower(), value.lower())
                elif row_type == 'f':
                    self.add_field_format(row_data)
                elif row_type == 'c':
                    self.add_check(row_data)
                elif row_type != '':
                    # Raise error when value is not supported.
                    raise errors.DataFormatSyntaxError('CID row type is "%s" but must be empty or one of: C, D, or F'
                                                       % row_type, self._location)
            self._location.advance_line()

    def add_field_format(self, items):
        """
        Add field as described by `items`. The meanings of the items are:

        1) field name
        2) optional: example value (can be empty)
        3) optional: empty flag ("X"=field is allowed to be empty)
        4) optional: length ("lower:upper")
        5) optional: field type
        6) optional: rule to validate field (depending on type)

        Further values in `items` are ignored.

        Any errors detected result in a `errors.FieldSyntaxError`.
        """
        assert items is not None
        assert self._location is not None

        if self._data_format is None:
            raise errors.CidSyntaxError("data format must be specified before first field", self._location)

        # Assert that the various lists and maps related to fields are in a consistent state.
        # Ideally this would be a class invariant, but this is Python, not Eiffel.
        field_count = len(self.field_names)
        assert len(self._field_formats) == field_count
        assert len(self._field_name_to_format_map) == field_count
        assert len(self._field_name_to_index_map) == field_count

        field_name = None
        field_example = None
        field_is_allowed_to_be_empty = False
        field_length = None
        field_type = None
        field_rule = ""

        item_count = len(items)
        if item_count >= 1:
            # Obtain field name.
            field_name = fields.validated_field_name(items[0], self._location)

            # Obtain example.
            if item_count >= 2:
                self._location.advance_cell()
                field_example = items[1]

            # Obtain "empty" flag.
            if item_count >= 3:
                self._location.advance_cell()
                field_is_allowed_to_be_empty_text = items[2].strip().lower()
                if field_is_allowed_to_be_empty_text == self._EMPTY_INDICATOR:
                    field_is_allowed_to_be_empty = True
                elif field_is_allowed_to_be_empty_text:
                    raise errors.FieldSyntaxError("mark for empty field must be %r or empty but is %r"
                                                  % (self._EMPTY_INDICATOR,
                                                     field_is_allowed_to_be_empty_text), self._location)

            # Obtain length.
            if item_count >= 4:
                self._location.advance_cell()
                field_length = items[3].strip()

            # Obtain field type.
            if item_count >= 5:
                self._location.advance_cell()
                field_type_item = items[4].strip()
                if field_type_item:
                    field_type = ""
                    field_type_parts = field_type_item.split(".")
                    try:
                        for part in field_type_parts:
                            if field_type:
                                field_type += "."
                            field_type += _tools.validatedPythonName("field type part", part)
                        assert field_type, "empty field type must be detected by validatedPythonName()"
                    except NameError as error:
                        raise errors.FieldSyntaxError(str(error), self._location)

            # Obtain rule.
            if item_count >= 6:
                self._location.advance_cell()
                field_rule = items[5].strip()

            # Obtain class for field type.
            if not field_type:
                field_type = "Text"
            field_class = self._create_field_format_class(field_type)
            _log.debug("create field: %s(%r, %r, %r)", field_class.__name__, field_name, field_type, field_rule)
            field_format = field_class.__new__(field_class, field_name, field_is_allowed_to_be_empty, field_length, field_rule)
            field_format.__init__(field_name, field_is_allowed_to_be_empty, field_length, field_rule, self._data_format)

            # Validate that field name is unique.
            if field_name in self._field_name_to_format_map:
                self._location.set_cell(1)
                raise errors.FieldSyntaxError("field name must be used for only one field: %s" % field_name,
                                              self._location)

            # Set and validate example in case there is one.
            if field_example:
                try:
                    field_format.example = field_example
                except errors.FieldValueError as error:
                    self._location.set_cell(2)
                    raise errors.CidSyntaxError("cannot validate example for field %r: %s" % (field_name, error), self._location)

            # Validate field length for fixed format.
            if self._data_format.format == data.FORMAT_FIXED:
                self._location.set_cell(4)
                if field_format.length.items:
                    field_length_is_broken = True
                    if len(field_format.length.items) == 1:
                        (lower, upper) = field_format.length.items[0]
                        if lower == upper:
                            if lower < 1:
                                raise errors.FieldSyntaxError("length of field %r for fixed data format must be at least"
                                                              " 1 but is : %s" % (field_name, field_format.length),
                                                              self._location)
                            field_length_is_broken = False
                    if field_length_is_broken:
                        raise errors.FieldSyntaxError("length of field %r for fixed data format must be a single value"
                                                      " but is: %s" % (field_name, field_format.length), self._location)
                else:
                    raise errors.FieldSyntaxError("length of field %r must be specified with fixed data format" % field_name,
                                                  self._location)

            self._location.set_cell(1)
            self._field_name_to_format_map[field_name] = field_format
            self._field_name_to_index_map[field_name] = len(self._field_names)
            self._field_names.append(field_name)
            self._field_formats.append(field_format)
            # TODO: Remember location where field format was defined to later include it in error message
            _log.info("%s: defined field: %s", self._location, field_format)
        else:
            raise errors.FieldSyntaxError("field format row (marked with %r) must at least contain a field name"
                                          % self._ID_FIELD_RULE, self._location)

        assert field_name
        assert field_type
        assert field_rule is not None

    def add_check(self, items):
        assert items is not None

        item_count = len(items)
        if item_count < 2:
            raise errors.CheckSyntaxError("check row (marked with %r) must contain at least 2 columns" % self._ID_CHECK,
                                          self._location)
        check_description = items[0]

        # HACK: skip blank cells between `description` and `type` when `description` has concatenated cells
        check_type = None
        rule_index = 2
        for i in range(1, len(items)):
            check_class_name = items[i] + "Check"
            if check_class_name in self._check_name_to_class_map:
                check_type = items[i]
                rule_index = i + 1
        if not check_type:
            raise errors.CheckSyntaxError("check type should be one of %s but is %s"
                                          % (self._check_name_to_class_map.keys(), items[1:-2]), self._location)
        if item_count >= 3:
            check_rule = items[rule_index]  # default 2
        else:
            check_rule = ""
        _log.debug("create check: %s(%r, %r)", check_type, check_description, check_rule)
        check_class = self._create_check_class(check_type)
        check = check_class.__new__(check_class, check_description, check_rule, self._field_names, self._location)
        check.__init__(check_description, check_rule, self._field_names, self._location)
        self._location.set_cell(1)
        existing_check = self._check_name_to_check_map.get(check_description)
        if existing_check is not None:
            raise errors.CheckSyntaxError("check description must be used only once: %r" % check_description,
                                          self._location, "initial declaration", existing_check.location)
        self._check_name_to_check_map[check_description] = check
        self._check_names.append(check_description)
        assert len(self.check_names) == len(self._check_name_to_check_map)

    def field_index(self, field_name):
        """
        The column index of  the field named ``field_name`` starting with 0.
        """
        assert field_name is not None
        try:
            result = self._field_name_to_index_map[field_name]
        except KeyError:
            raise errors.FieldLookupError("unknown field name %r must be replaced by one of: %s"
                                          % (field_name, _tools.humanReadableList(sorted(self.field_names))))
        return result

    def field_value_for(self, field_name, row):
        """
        The value for field ``field_name`` in ``row``. This looks up the column of the field named
        ``field_name`` and retrieves the data from the matching item in ``row``. If ``row`` does
        not contain the expected amount of field value, raise a `errors.DataFormatValueError`.
        """
        assert field_name is not None
        assert row is not None

        actual_row_count = len(row)
        expected_row_count = len(self.field_names)
        if actual_row_count != expected_row_count:
            self._location = errors.create_caller_input_location()
            raise errors.DataFormatValueError("row must have %d items but has %d: %s"
                                              % (expected_row_count, actual_row_count, row), self._location)

        field_index = self.get_field_name_index(field_name)
        # The following condition must be ``True`` because any deviations should be been detected
        # already by comparing expected and actual row count.
        assert field_index < len(row)

        result = row[field_index]
        return result

    def field_format_for(self, field_name):
        """
        The `fields.AbstractFieldFormat` for ``field_name``. If no such field has been defined,
        raise a ``KeyError`` .
        """
        assert field_name is not None
        return self._field_name_to_format_map[field_name]

    def field_format_at(self, field_index):
        """
        The `fields.AbstractFieldFormat` at ``field_index``. If no such field has been defined,
        raise an ``IndexError`` .
        """
        assert field_index is not None
        return self._field_formats[field_index]

    def check_for(self, check_name):
        """
        The `checks.AbstractCheck` for ``check_name``. If no such check has been defined,
        raise a ``KeyError`` .
        """
        assert check_name is not None
        return self._check_name_to_check_map[check_name]
