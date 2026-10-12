"""Macro Research Analyst: a two-agent CrewAI crew on EconDash data.

    pip install crewai-econdash
    export MODEL=gpt-4.1-mini OPENAI_API_KEY=...   # any model CrewAI supports
    python examples/crewai_macro_research.py DEU

The researcher pulls figures with the EconDash tools; the analyst writes a short brief
that cites each figure with its econdash.org chart link. Without ECONDASH_API_KEY the
crew runs on the free trial (10 countries, 50 indicators).
"""

import sys

from crewai import Agent, Crew, Process, Task
from crewai_econdash import EconDashCompareTool, EconDashSearchTool, EconDashSeriesTool

from econdash import EconDash

country = sys.argv[1] if len(sys.argv) > 1 else "DEU"
client = EconDash()

researcher = Agent(
    role="Macro data researcher",
    goal=f"Collect current, sourced macro figures for {country} from EconDash",
    backstory="You only report numbers a tool returned, with the chart link it gave.",
    tools=[
        EconDashSearchTool(client=client),
        EconDashSeriesTool(client=client),
        EconDashCompareTool(client=client),
    ],
)
analyst = Agent(
    role="Macro research analyst",
    goal="Write a short, accurate country brief from the researcher's notes",
    backstory="You never add a figure that is not in the notes.",
)

collect = Task(
    description=(
        f"For {country} (ISO3), find and load GDP growth, CPI inflation and unemployment with "
        "the EconDash tools: search first, pick the best slug among several matches, then "
        "load the series. Compare GDP growth "
        "with USA and JPN. If a tool says payment is required, write that down instead of a "
        "number."
    ),
    expected_output="Notes: indicator, latest value, date, unit and the econdash.org chart link.",
    agent=researcher,
)
brief = Task(
    description=(
        f"Write a brief on the {country} economy from the notes. Every figure has its date "
        "and is followed by its econdash.org link in brackets. End with 'Source: EconDash "
        "(econdash.org)'."
    ),
    expected_output="Markdown, 150-250 words, with figures and econdash.org links.",
    agent=analyst,
    context=[collect],
)

if __name__ == "__main__":
    crew = Crew(
        agents=[researcher, analyst],
        tasks=[collect, brief],
        process=Process.sequential,
        verbose=True,
    )
    print(crew.kickoff())
