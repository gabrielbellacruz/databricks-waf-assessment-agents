"""Analytics checks. Importing this package registers every check.

Every check module in this directory is imported automatically (which runs its
``@register`` decorator), so adding a check is just dropping a new module here -
no edit to this file is needed. One module per question.
"""

from __future__ import annotations

import importlib
import pkgutil

# Import every sibling module so each check's @register decorator runs.
for _module in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_module.name}")
