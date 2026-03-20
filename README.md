# AILogAnalyzer

別プロジェクトのサービスログを定期同期し、Claude Code（AIエージェント）で監視・Discord報告するシステム。

## アーキテクチャ

- **log-sync** (コンテナA): rsync でリモートサーバーからログを同期（ワンショット実行）
- **ai-agent** (コンテナB): Claude Code でログを分析し Discord に報告（デーモン）
- **systemd timer**: ホスト側でスケジューリング（sync: 15分毎、analysis: 6時間毎）

## セットアップ

### 1. シークレット配置

```bash
cp .env.example .env  # 必要に応じて編集

# secrets/ に以下を配置:
#   ssh_private_key   — rsync用SSH秘密鍵
#   ssh_passphrase    — SSH鍵のパスフレーズ
#   discord_webhook_url — Discord Webhook URL
```

### 2. ビルド

```bash
docker compose build
```

### 3. Claude Code 認証（初回のみ）

```bash
docker compose up -d ai-agent
docker compose exec ai-agent su - claude -c "claude auth login"
# 表示されるURLをブラウザで開いて認証を完了
```

### 4. 動作確認

```bash
# ログ同期テスト
docker compose run --rm log-sync-webserver

# AI分析テスト
docker compose exec -T ai-agent /usr/local/bin/analyze.sh
```

### 5. systemd タイマー設定

```bash
sudo systemd/install.sh
systemctl list-timers ailog-*
```

## 構成

```
AILogAnalyzer/
├── docker-compose.yml
├── .env.example
├── log-sync/          # コンテナA: ログ同期
├── ai-agent/          # コンテナB: AI分析・Discord通知
├── systemd/           # systemd ユニットファイル
└── secrets/           # シークレット（git-ignored）
```

## ログ確認

```bash
journalctl -u ailog-sync-webserver.service
journalctl -u ailog-agent.service
```
