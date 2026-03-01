# Use an official Python 3.11 slim image as a parent image
FROM python:3.11-slim

# Set the working directory in the container to /app
WORKDIR /app

# Install uv using pip. This is the recommended way to bootstrap uv.
RUN pip install uv

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install packages specified in requirements.txt using uv.
# The --system flag installs them into the global site-packages, similar to pip.
RUN uv pip install --system --no-cache -r requirements.txt

# Copy the rest of your application's source code into the container
COPY . .

# Make port 8080 available to the world outside this container.
# Cloud Run uses the PORT environment variable, which defaults to 8080.
EXPOSE 8080

# Run main.py when the container launches.
# Your main.py is already configured to start uvicorn on the host and port specified by Cloud Run.
CMD ["python", "main.py"]