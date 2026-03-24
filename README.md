# AILogAnalyzer

## Prepare

```bash
cp ./docker-compose.yml.example ./docker-compose.yml
```

edit.

```bash
vi ./docker-compose.yml
touch ./secrets/ssh_passphrase_a && chmod 600 ./secrets/ssh_passphrase_a
vi ./secrets/ssh_passphrase_a
```

init ai-agent.

```bash
SERVICE_NAME=xxxxx
sudo bash ai-agent/docker_run.sh ${SERVICE_NAME} # --delete # create image, run, auth subscription
# sudo docker exec -it -u claude ailog-agent-${SERVICE_NAME} claude --dangerously-skip-permissions
# sudo docker stop ailog-agent-${SERVICE_NAME} && sudo docker rm ailog-agent-${SERVICE_NAME} 
# sudo docker rmi ailog-agent && sudo docker system prune -a
```

## Test Run

```bash
sudo docker compose up && sudo docker compose down
```

```bash
SERVICE_NAME=xxxxx
sudo docker exec -t ailog-agent-${SERVICE_NAME} /tools/analyze.sh --max-lines 100000 --mention "<@12345678901234567890>"
sudo docker exec -t ailog-agent-${SERVICE_NAME} python3 /tools/status.py --all
sudo docker exec -t ailog-agent-${SERVICE_NAME} bash -c '/tools/search-logs.sh /data/logs/ 2>/dev/null | python3 /tools/summarize-logs.py -' > ./tmp.summary 2>&1
```

## Schedule

```bash
sudo bash ./systemd/install.sh
# sudo systemctl start ailog-sync.service
# sudo journalctl -u ailog-sync.timer
# sudo journalctl -u ailog-sync.service
```

```bash
sudo bash ./systemd/register-agent.sh ${SERVICE_NAME}
```
