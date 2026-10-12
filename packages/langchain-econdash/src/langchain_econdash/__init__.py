"""LangChain tools for the EconDash API.

Data access is the econdash client's access. Nothing here bypasses the trial,
an API key, or pay-per-call.
"""

from langchain_econdash.toolkit import EconDashToolkit

__version__ = "0.1.1"
__all__ = ["EconDashToolkit", "__version__"]
