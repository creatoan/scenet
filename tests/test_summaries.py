"""How a validation error is told, when nothing in the document can be pointed at (#345).

Every fault a document gives has a path, so no finding showed the root's name, and the
mutation run found it unheld.
"""

import pytest
from pydantic import ValidationError

from scenet.frontends.common import summarise
from scenet.ir import PanelIR


def test_a_fault_of_the_whole_document_is_at_its_root():
    with pytest.raises(ValidationError) as caught:
        PanelIR.model_validate(3)
    assert summarise(caught.value) == (
        "invalid panel:\n  at <root>: Input should be a valid dictionary or instance of PanelIR"
    )
