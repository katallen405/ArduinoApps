FROM python:3.13-slim
RUN pip install --no-cache-dir msgpack legoeducation
COPY agent.py /srv/agent.py
CMD ["python", "-u", "/srv/agent.py"]
