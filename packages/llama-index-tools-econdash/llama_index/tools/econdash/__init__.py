"""LlamaIndex tools and a reader for the EconDash API.

Data access is the econdash client's access. Nothing here bypasses the trial,
an API key, or pay-per-call. A series whose licence forbids redistribution
is left out of the reader.
"""

from llama_index.tools.econdash.reader import EconDashReader
from llama_index.tools.econdash.spec import EconDashToolSpec

__version__ = "0.1.0"
__all__ = ["EconDashReader", "EconDashToolSpec", "__version__"]
