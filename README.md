# AILogAnalyzer


```bash
sudo docker compose up && sudo docker compose down
```

```bash
sudo bash ai-agent/docker_run.sh servicename
# sudo docker exec -it -u claude ailog-agent-{servicename} claude --dangerously-skip-permissions
```

```bash
SERVICE_NAME=xxxxx
sudo docker exec -t ailog-agent-${SERVICE_NAME} /tools/analyze.sh 100000
sudo docker exec -t ailog-agent-${SERVICE_NAME} python3 /tools/status.py --all
```
