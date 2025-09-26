# Use Python image with pre-installed uv as base image
FROM ghcr.io/astral-sh/uv:python3.13-alpine

# Set working directory to /app
WORKDIR /app

# Enable bytecode compilation to improve Python code execution performance
ENV UV_COMPILE_BYTECODE=1

# Set link mode to copy instead of link because this is a mounted volume
ENV UV_LINK_MODE=copy

# Install project dependencies using lock file and settings (excluding the project itself)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Then, add the rest of the project source code and install
# Separate dependency installation from project installation for optimal layer caching
COPY . /app
# Install the project (excluding development dependencies)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Put executables from virtual environment at the front of PATH environment variable
ENV PATH="/app/.venv/bin:$PATH"

# Set the port number for the application to run
ENV PORT=8081

# Reset entrypoint to not call uv command
ENTRYPOINT []

# Run the application directly using Python from virtual environment
CMD ["python", "server.py"]
