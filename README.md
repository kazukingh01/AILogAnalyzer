# AILogAnalyzer

```bash
sudo docker build -t ailog-agent ./ai-agent
sudo docker run -d --name ailog-agent \
  --env-file .env \
  -v ./logs:/data/logs:ro \
  ailog-agent
sudo docker exec -it -u claude ailog-agent claude --dangerously-skip-permissions
```


