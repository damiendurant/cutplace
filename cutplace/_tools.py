"""
Various internal utility functions.
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
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import errno
import logging
import os
import platform
import io
import token
import tokenize


# Mapping for value of --log to logging level.
LOG_LEVEL_NAME_TO_LEVEL_MAP = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL
}

NUMBER_DECIMAL_COMMA = "decimalComma"
NUMBER_DECIMAL_POINT = "decimalPoint"
NUMBER_INTEGER = "integer"


def mkdirs(folder):
    """
    Like ``os.mkdirs()`` but does not raise an `OSError` if ``folder`` already exists.
    """
    assert folder is not None

    try:
        os.makedirs(folder)
    except OSError as error:
        if error.errno != errno.EEXIST:
            raise


def attemptToRemove(filePath):
    """
    Like ``os.remove()`` but does not raise an `OSError` if ``filePath`` does not exist.
    """
    assert filePath is not None

    try:
        os.remove(filePath)
    except OSError as error:
        if error.errno != errno.EEXIST:
            raise


def validatedPythonName(name, value):
    """
    Validated and cleaned up `value` that represents a Python name with any whitespace removed.
    If validation fails, raise `NameError` with mentioning ``name`` as the name under which
    ``value`` is known to the user.
    """
    assert name
    assert value is not None

    readable = io.StringIO(value.strip())
    toky = tokenize.generate_tokens(readable.readline)
    nextToken = next(toky)
    nextType = nextToken[0]
    result = nextToken[1]
    if tokenize.ISEOF(nextType):
        raise NameError("%s must not be empty but was: %r" % (name, value))
    if nextType != token.NAME:
        raise NameError("%s must contain only ASCII letters, digits and underscore (_) but is: %r"
                        % (name, value))
    secondToken = next(toky)
    secondTokenType = secondToken[0]
    if not tokenize.ISEOF(secondTokenType):
        raise NameError("%s must be a single word, but after %r there also is %r" % (name, result, secondToken[1]))
    return result


def platformVersion():
    macVersion = platform.mac_ver()
    if (macVersion[0]):
        result = "Mac OS %s (%s)" % (macVersion[0], macVersion[2])
    else:
        result = platform.platform()
    return result


def pythonVersion():
    return platform.python_version()


def humanReadableList(items):
    """
    All values in `items` in a human readable form. This is meant to be used in error messages, where
    dumping "%r" to the user does not cut it.
    """
    assert items is not None
    itemCount = len(items)
    if itemCount == 0:
        result = ""
    elif itemCount == 1:
        result = "%r" % items[0]
    else:
        result = ""
        for itemIndex in range(itemCount):
            if itemIndex == itemCount - 1:
                result += " or "
            elif itemIndex > 0:
                result += ", "
            result += "%r" % items[itemIndex]
        assert result
    assert result is not None
    return result


def tokenizeWithoutSpace(text):
    """
    ``text`` split into token with any white space tokens removed.
    """
    assert text is not None
    for toky in tokenize.generate_tokens(io.StringIO(text).readline):
        tokyType = toky[0]
        tokyText = toky[1]
        if ((tokyType != token.INDENT) and tokyText.strip()) or (tokyType == token.ENDMARKER):
            yield toky


def tokenText(toky):
    assert toky is not None
    tokyType = toky[0]
    tokyText = toky[1]
    if tokyType == token.STRING:
        result = tokyText[1:-1]
    else:
        result = tokyText
    return result


def isEofToken(someToken):
    """
    True if `someToken` is a token that represents an "end of file".
    """
    assert someToken is not None
    return tokenize.ISEOF(someToken[0])


def isCommaToken(someToken):
    """
    True if `someToken` is a token that represents a comma (,).
    """
    assert someToken
    return (someToken[0] == token.OP) and (someToken[1] == ",")


def withSuffix(path, suffix=""):
    """
    Same as `path` but with suffix changed to `suffix`.

    Examples:

    >>> withSuffix("eggs.txt", ".rst")
    'eggs.rst'
    >>> withSuffix("eggs.txt", "")
    'eggs'
    >>> withSuffix(os.path.join("spam", "eggs.txt"), ".rst")
    'spam/eggs.rst'
    """
    assert path is not None
    assert suffix is not None
    result = os.path.splitext(path)[0]
    if suffix:
        result += suffix
    return result