# Building-Multi-Agent-Systems
This project demonstrates how to break down a complex, multi-step engineering task and delegate it to a team of intelligent, specialized agents. This architecture uses a coordinated swarm of agents working together to solve a problem and synthesize the results

**Use Case: Automated Incident Response**
A DevOps engineer responding to an urgent production incident. They are looking at a cryptic application error and a dense stack trace.
Instead of manually digging through logs and Git histories, the engineer simply pastes the stack trace into Gemini CLI.

1. CLI intelligently delegates the investigation to our custom Root Agent.
2. The Root Agent extracts the specific file name and error signature from the stack trace.
3. It dispatches two parallel sub-agents: one hunts down historical error matches, known root causes, and solutions, while the other pulls the latest Git commits for the exact file that crashed.
4. A final Merger Agent synthesizes these findings into a unified, actionable incident report and streams it right back to the engineer's CLI.

**System Architecture**
This project operates as a specialized sub-agent that seamlessly integrates with the Gemini CLI via the Agent-to-Agent (A2A) protocol.

The execution flow follows this precise chain:
User CLI ➔ A2A Protocol ➔ ADK Sub-Agent hosted on Vertex AI Agent Engine
Once the payload reaches the Agent Engine, our custom orchestration takes over:
Root Sequential Agent: Acts as the manager, receiving the initial stack trace and orchestrating the workflow.

Parallel Gatherer Agent:
AlloyDB Agent: Find matching historical errors and documented solutions through semantic (vector) search.
Git Agent: Connects to the repository to find recent code changes or broken commits on the extracted file. Please note that this step is mocked by saving a local git JSON file in a cloud storage bucket. 

Merger Agent: Waits for the parallel agents to finish, ingests their raw data, and writes the final Markdown troubleshooting report.

The formatted report is streamed back up the A2A chain to the user's CLI.

**Technologies Used**
Gemini CLI: The primary user interface and top-level routing agent.
A2A (Agent-to-Agent) Protocol: The communication layer that allows the CLI to securely delegate tasks to remote sub-agents.
ADK (Agent Development Kit): The Python framework used to define the ParallelAgent, SequentialAgent, and internal routing logic.
Vertex AI Agent Engine: The serverless Google Cloud runtime environment hosting our ADK sub-agent architecture.
Google Cloud AlloyDB: The enterprise PostgreSQL-compatible database queried by the agents to retrieve historical error logs and solutions.

**Installation & Setup** 
Tested and verified to work on Google Cloud Platform (GCP) using cloud shell to create and deploy the required resources

1- Clone the Repository

git clone https://github.com/8amadel/Building-Multi-Agent-Systems.git

2- Set your environment variables in Building-Multi-Agent-Systems/config.env

3- Authenticate

gcloud auth login

gcloud auth application-default login

Accept all actions by always answering with "y", follow the prompt by opening the provided link in a browswer, tick all the checkboxes and copy the code back to the terminal.

4- Make the scripts executable and run the single deployment command

cd Building-Multi-Agent-Systems/

find . -type f -name "*.sh" -exec chmod u+x {} +

nohup ./fullDeploy.sh &

5- Monitor the nohup.out file, you might get some warnings that could be safely ignored. The file should show a similar output when the script's work is done
Constructing agent card and setting in .md file
Deployment Completed!

6- Test using gemini CLI

export MAS_TOKEN=$(gcloud auth print-access-token)

gemini

/agents reload

/agents list

Use your sub-agent mas_agent to troubleshoot the following error:
Exception in thread 'main' TimeoutException: at com.system.SchemaMigrator.execute(SchemaMigrator.py:80).
Only delegate to the subagent and display its output without changing it or doing anything else.
