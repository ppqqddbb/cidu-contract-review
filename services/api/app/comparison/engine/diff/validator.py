from ..diff.equal_shield import has_real_change, normalized_equal
from ..models.diff import ChangeItem


def validate_change(change: ChangeItem) -> bool:
    if normalized_equal(change.old_text, change.new_text):
        return False
    if not has_real_change(change.operations):
        return False
    return True

