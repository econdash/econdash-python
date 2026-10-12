"""CrewAI tools for the EconDash API.

Data access is the econdash client's access. Nothing here bypasses the trial,
an API key, or pay-per-call.
"""

from crewai_econdash.tools import EconDashCompareTool, EconDashSearchTool, EconDashSeriesTool

__version__ = "0.1.2"
__all__ = ["EconDashCompareTool", "EconDashSearchTool", "EconDashSeriesTool", "__version__"]
