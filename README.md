# TeleTrans

TeleTrans is a Telegram bot that listens to messages from a configured source channel and forwards translated Arabic messages to a destination channel.

## What it does
- Watches one or more configured source channels
- Detects Arabic text
- Translates it to Hebrew
- Sends the translated message to a destination channel
- Supports media attachments such as photos and documents
- Completes messages missed while the process was offline

## Project structure
- app/ - application logic
- data/ - persistent runtime data such as sessions and config
- tests/ - basic regression tests

## Requirements
- Python 3.13+
- Docker and Docker Compose (recommended)
- Telegram API credentials from https://my.telegram.org

## Local setup
1. Create a virtual environment
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a .env file with:
   ```env
   API_ID=your_api_id
   API_HASH=your_api_hash
   PHONE=your_phone_number
   SUPABASE_URL=your_project_url
   SUPABASE_KEY=your_service_role_key
   ```
4. Configure data/config.json
5. Run the bot:
   ```bash
   python -m app.main
   ```

## Docker setup
Build and run with:
```bash
docker compose up -d
```

The container uses the local data directory for sessions and config.

## Missed-message completion
The bot keeps a separate Telegram message checkpoint for every source channel.
On the first run it starts at the newest existing message. On later runs it
processes every message after the saved checkpoint, from oldest to newest.

Without Supabase credentials, checkpoints are stored locally in
`data/checkpoints.json`. For ephemeral hosting such as Render, run
`supabase/migrations/001_channel_checkpoints.sql` in the Supabase SQL editor and
configure `SUPABASE_URL` and a server-side `SUPABASE_KEY` environment variable.
Never expose the service-role key in frontend code or commit it to Git.

## External server deployment
For a server deployment, prepare the following:
- A Linux server with Docker installed
- A persistent folder for data
- A .env file with your Telegram credentials
- Optional: a reverse proxy if you later expose a web UI

Example deployment flow:
```bash
git clone https://github.com/relzabari/TeleTrans.git
cd TeleTrans
git checkout main
mkdir -p data/sessions
cp .env.example .env
nano .env
sudo docker compose up -d
```

## Important notes
- Keep your Telegram credentials private
- Do not commit .env or session files to GitHub
- The project currently focuses on a single translation workflow and does not yet add multi-channel management

## Testing
Run:
```bash
python -m unittest discover -s tests -v
```
