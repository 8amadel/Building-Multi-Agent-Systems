from google import adk
from google.adk.agents.parallel_agent import ParallelAgent
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.sequential_agent import SequentialAgent
from functools import cached_property
import os
from google.cloud import storage
import json
import asyncio
import google.auth
from google.auth.transport.requests import Request
from google.adk.models import Gemini
from google.genai import Client, types
from pydantic import BaseModel, Field
import logging
from collections.abc import Awaitable, Callable
from typing import Any, NoReturn
from a2a.client import ClientConfig, ClientFactory
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    AgentSkill,
    Message,
    Part,
    Role,
    TaskState,
    TextPart,
    TransportProtocol,
    UnsupportedOperationError,
)
from a2a.utils import new_agent_text_message
from a2a.utils.errors import ServerError
from google.adk import Runner
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService
from google.adk.tools import google_search_tool
from vertexai.preview.reasoning_engines import A2aAgent
from vertexai.preview.reasoning_engines.templates.a2a import create_agent_card
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset 
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

logging.getLogger().setLevel(logging.INFO)

### Override Gemini Class to enable global endpoint for preview models

class Gemini3(Gemini):

    @cached_property
    def api_client(self) -> Client:

        project =  os.getenv("GOOGLE_CLOUD_PROJECT")
        print(f"Project: {project}")
        location = "global"

        return Client(
            vertexai=True,
            project=project,
            location=location,
            http_options=types.HttpOptions(
                headers=self._tracking_headers(),
                retry_options=self.retry_options,
            )
        )


PROJECT_ID = os.environ.get("PROJECT_ID")
REGION_ID = os.environ.get("REGION_ID")
CLUSTER_ID = os.environ.get("ALLOYDB_CLUSTER_NAME")
INSTANCE_ID = os.environ.get("ALLOYDB_INSTANCE_NAME")
DATABASE_ID = os.environ.get("ALLOYDB_DATABASE_NAME")
GEMINI_MODEL="PHGM"
mcp_url = f"https://alloydb.{REGION_ID}.rep.googleapis.com/mcp"

# Configure auth for AlloyDB MCP Server
def get_dynamic_auth_headers(ctx=None):
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(Request())
    
    return {
        "Authorization": f"Bearer {credentials.token}",
        "X-Goog-User-Project": PROJECT_ID
    }

mcp_params = StreamableHTTPConnectionParams(
    url=mcp_url,
    headers={
        "Content-Type": "application/json"
    }
)

alloydb_toolset = McpToolset(
    connection_params=mcp_params,
    header_provider=get_dynamic_auth_headers
)

# Tool for Git Agent
def get_latest_commits_on_file(filename: str, limit: int = 3):
    """
    Tool to retrieve the most recent commits for a specific file 
    by reading from the remote GCS mock repository.
    """
    bucket_name = f"{PROJECT_ID}-mock-git-repo" 
    
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob("git_history.json")
    
    # Download the json as a string
    data_string = blob.download_as_text()
    repo_history = json.loads(data_string)
    
    # Find the commits for the requested file
    file_commits = repo_history.get(filename, [])
    
    # Return only the top N recent commits
    return file_commits[:limit]


alloydb_agent = LlmAgent(
    model=Gemini3(model=GEMINI_MODEL),
    name='alloydb_agent',
    instruction=f"""
    You are an expert data retrieval agent. Your job is to translate a user's natural language search 
    into a SQL vector search query and execute it using the `execute_sql` tool.

    CRITICAL INSTRUCTION FOR TOOL CALL:
    When calling the `execute_sql` tool, you MUST include these three specific parameters exactly as named. Do not omit them:
    1. `instance`: "projects/{PROJECT_ID}/locations/{REGION_ID}/clusters/{CLUSTER_ID}/instances/{INSTANCE_ID}"
    2. `database`: "{DATABASE_ID}"
    3. `sqlStatement`: The raw SQL vector search query string.

    **Database Schema:**
    Table: `public.troubleshooting_kb`
    Columns:     
    error_id SERIAL PRIMARY KEY,
    stack_trace TEXT NOT NULL,
    root_cause TEXT NOT NULL,
    solution TEXT NOT NULL,
    stack_trace_embedding vector(768)

    **Rules for Vector Search:**
    1. To convert the user's natural language search text into a vector, use the built-in AlloyDB Vertex AI function:
       `embedding('text-embedding-005', 'THE_SEARCH_TEXT')::vector`
    2. Calculate similarity using the cosine distance operator `<=>`. The formula is:
       `1 - (embedding <=> query_vector)`
    3. You must ONLY return results with 70% or higher similarity. 
       Filter using: `WHERE 1 - (embedding <=> query_vector) >= 0.70`
    4. Return the `stack_trace`, `root_cause`, `solution`, and `similarity_score`, ordered by similarity descending.

    CRITICAL SQL RULE:
    The `embedding()` function returns a real array, but the `<=>` operator requires a vector. 
    You MUST explicitly cast the embedding to a vector by appending `::vector`. 
    - BAD: embedding('text-embedding-005', 'text')
    - GOOD: embedding('text-embedding-005', 'text')::vector
    
    STRICTLY Format the final output as json with the following keys:
    stack_trace 1, similarity_score 1, root_cause 1, solution 1, stack_trace 2, similarity_score 2, root_cause 2, solution 2, ...
    DO NOT RETURN ANYTHING OTHER THAN THE FINAL JSON OUTPUT.
    """,
    tools=[alloydb_toolset],
    output_key="alloydb_result"
)

git_agent = LlmAgent(
    model=Gemini3(model=GEMINI_MODEL),
    name='git_agent',
    instruction=f"""
    You are a git retreiver agent. Your ONLY role is to extract the culprit file name from a stack trace
    then use your tool to find the latest commit information on that file formatted as a JSON array. 
    Return all the information provided by your tool, do not omit anything.
    DO NOT RETURN ANYTHING OTHER THAN THE FINAL JSON OUTPUT
    """,
    tools=[get_latest_commits_on_file],
    output_key="git_result"
)

parallel_troubleshooting_agent = ParallelAgent(
    name="parallel_troubleshooting_agent",
    sub_agents=[alloydb_agent, git_agent],
    description="Runs multiple troubleshooting agents in parallel to gather information."
)

merger_agent = LlmAgent(
     name="merger_agent",
     model=Gemini3(model=GEMINI_MODEL),
     instruction="""
     You are an agent responsible for combining error troubleshooting findings into a structured report.
     Your primary task is to combine the returned stack traces,similarity scores, root causes and solutions 
     with the changes done on the file on GIT and present an action plan to the end user.

     **Crucially: Your entire response MUST be grounded *exclusively* on the information provided in the 'Input Summaries' below. Do NOT add any external knowledge, facts, or details not present in these specific summaries.**

     **Input Summaries:**

     *   **Matched Previously Seen Errors and their Solutions:**
         {alloydb_result}

     *   **Latest Commits on Reported File:**
         {git_result}
    
     The output should exactly match the following Output Format:
     ** Output Format:

     Stack trace <stack_trace> <similarity score> % matches your error. The root cause is <root_cause>
     and the solution is <solution>.

     File <file_name> extracted from your stack trace was last updated on <last_commit_date> by <author> and 
     the commit message is <message>.
     """,
     description="Combines troubleshooting findings from parallel agents strictly grounded on provided inputs.",
 )

sequential_pipeline_agent = SequentialAgent(
     name="sequential_pipeline_agent",
     # Run parallel research first, then merge
     sub_agents=[parallel_troubleshooting_agent, merger_agent],
     description="Coordinates parallel troubleshooting and synthesizes the results."
 )

root_agent = sequential_pipeline_agent

#Agent Card
mas_agent_skill = AgentSkill(
    id="mas_agent_skill",
    name="mas_agent_skill",
    description="Match an error with previous reported errors and try to find root causes and solutions based on matching the error with the previous reported errors and the latest commits on the file reported in the stack trace.",
    tags=["GIT", "Troubleshooting", "Error","Similarity"],
    examples=[
        "Find the root cause and the solution of the following error:",
    ],
    input_modes=["text/plain"],
    output_modes=["text/plain"],
)

mas_agent_card = create_agent_card(
    agent_name="mas_agent",
    description="An agent responsible for matching an error stack trace with previously reported errors and try to find root causes and solutions based on matching the error with the previous reported errors and the latest commits on the file reported in the stack trace.",
    skills=[mas_agent_skill],
)
### Define the agent executor
class masAgentExecutor(AgentExecutor):
    def __init__(self) -> None:
        self.agent = None
        self.runner = None

    def _init_agent(self) -> None:
        if self.agent is None:
            self.agent = sequential_pipeline_agent
            self.runner = Runner(
                app_name=self.agent.name,
                agent=self.agent,
                artifact_service=InMemoryArtifactService(),
                session_service=InMemorySessionService(),
                memory_service=InMemoryMemoryService(),
            )

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        if self.agent is None:
            self._init_agent()

        query = context.get_user_input()
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)

        if not context.current_task:
            await updater.submit()

        await updater.start_work()

        try:
            session = await self._get_or_create_session(context.context_id)
            content = types.Content(role=Role.user, parts=[types.Part(text=query)])
            final_answer = None

            async for event in self.runner.run_async(
                session_id=session.id,
                user_id="user",  
                new_message=content,
            ):
                if event.is_final_response():
                    final_answer = self._extract_answer(event)

            if final_answer:
                await updater.add_artifact(
                    [TextPart(text=final_answer)],
                    name="answer",  
                )
                
            await updater.complete()

        except Exception as e:
            await updater.update_status(
                TaskState.failed, message=new_agent_text_message(f"Error: {e!s}")
            )
            raise

    async def _get_or_create_session(self, context_id: str):
        session = await self.runner.session_service.get_session(
            app_name=self.runner.app_name,
            user_id="user",
            session_id=context_id,
        )
        if not session:
            session = await self.runner.session_service.create_session(
                app_name=self.runner.app_name,
                user_id="user",
                session_id=context_id,
            )
        return session

    def _extract_answer(self, event) -> str:
        parts = event.content.parts
        text_parts = [part.text for part in parts if part.text]
        return " ".join(text_parts) if text_parts else "No answer found."

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> NoReturn:
        raise ServerError(error=UnsupportedOperationError())

### Wrap as an A2a Agent
a2a_agent = A2aAgent(agent_card=mas_agent_card, agent_executor_builder=masAgentExecutor)
a2a_agent.set_up()