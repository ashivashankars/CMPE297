# Container with Python + Node + Gemini CLI, serving the ADK dev UI/API on Cloud Run.
# Build from the "Assignment 3" folder:
#   docker build -f gemini_cli_agent/Dockerfile -t gemini-cli-adk .
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl git ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @google/gemini-cli \
    && rm -rf /var/lib/apt/lists/*

# Run as non-root: the CLI only ever touches /tmp/adk_gemini_cli_workspace.
RUN useradd -m agent
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY gemini_cli_agent ./gemini_cli_agent
USER agent
ENV PORT=8080 GEMINI_CLI_WORKSPACE=/tmp/adk_gemini_cli_workspace
EXPOSE 8080
CMD ["sh", "-c", "adk web --host 0.0.0.0 --port ${PORT} ."]
