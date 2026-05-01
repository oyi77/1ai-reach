#!/usr/bin/env python3
"""
Health Monitor for 1ai-reach
Checks all critical services and auto-recovers from failures
"""

import sys
import time
import subprocess
import sqlite3
import requests
from pathlib import Path
from datetime import datetime, timedelta

# Add scripts to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from config import DB_FILE, WAHA_API_KEY

# Service ports
MCP_PORT = 8766
WAHA_PORT = 3010

# Health check thresholds
MAX_RESPONSE_TIME = 5  # seconds
MAX_MEMORY_PERCENT = 90
MAX_DISK_PERCENT = 90
STUCK_MESSAGE_THRESHOLD = 300  # 5 minutes


def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def check_webhook_server():
    """Check if webhook server is responding"""
    try:
        response = requests.get(
            f"http://localhost:{MCP_PORT}/health", timeout=MAX_RESPONSE_TIME
        )
        return response.status_code == 200
    except:
        return False


    try:
        response = requests.get(
            timeout=MAX_RESPONSE_TIME,
        )
        return response.status_code == 200
    except:
        return False


def check_waha():
    """Check if WAHA is accessible"""
    try:
        response = requests.get(
            f"https://waha.aitradepulse.com/api/sessions",
            headers={"X-Api-Key": WAHA_API_KEY},
            timeout=MAX_RESPONSE_TIME,
        )
        return response.status_code == 200
    except:
        return False


def check_cloudflare_tunnel():
    """Check if Cloudflare tunnel is connected"""
    try:
        response = requests.get(
            "https://engage-mcp.aitradepulse.com/health", timeout=MAX_RESPONSE_TIME
        )
        return response.status_code == 200
    except:
        return False


def check_database():
    """Check database connectivity and locks"""
    try:
        conn = sqlite3.connect(str(DB_FILE), timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        conn.close()
        return True
    except:
        return False


def check_stuck_conversations():
    """Check for conversations stuck waiting for response"""
    try:
        conn = sqlite3.connect(str(DB_FILE), timeout=5)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM conversations 
            WHERE status = 'waiting_response' 
            AND last_message_at < datetime('now', '-5 minutes')
        """)
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except:
        return 0


def restart_webhook_server():
    """Restart webhook server"""
    log("🔄 Restarting webhook server...")
    subprocess.run(["pkill", "-f", "webhook_server.py"], capture_output=True)
    time.sleep(2)
    subprocess.Popen(
        ["python3", str(SCRIPT_DIR.parent / "webhook_server.py")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    time.sleep(3)


    time.sleep(2)
    subprocess.Popen(
        [
            "run",
            "--server.port",
            "--server.address",
            "0.0.0.0",
            "--server.headless",
            "true",
        ],
        cwd=str(SCRIPT_DIR.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    time.sleep(5)


def clear_duplicate_messages():
    """Clear duplicate/stuck messages from queue"""
    try:
        conn = sqlite3.connect(str(DB_FILE), timeout=5)
        cursor = conn.cursor()

        # Delete old duplicate detection cache
        cursor.execute("""
            DELETE FROM conversation_messages 
            WHERE created_at < datetime('now', '-1 hour')
            AND id NOT IN (
                SELECT MIN(id) FROM conversation_messages 
                GROUP BY conversation_id, message_text
            )
        """)

        conn.commit()
        conn.close()
        log("🧹 Cleared old messages")
    except Exception as e:
        log(f"⚠️ Failed to clear messages: {e}")


def check_disk_space():
    """Check available disk space"""
    try:
        result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True)
        lines = result.stdout.strip().split("\n")
        if len(lines) > 1:
            parts = lines[1].split()
            usage = parts[4].replace("%", "")
            return int(usage) < MAX_DISK_PERCENT
    except:
        pass
    return True


def rotate_logs():
    """Rotate logs if too large"""
    log_dir = SCRIPT_DIR.parent / "logs"
    for log_file in log_dir.glob("*.log"):
        size_mb = log_file.stat().st_size / (1024 * 1024)
        if size_mb > 100:  # 100MB
            log(f"🔄 Rotating {log_file.name}")
            # Rename old log
            backup = log_file.with_suffix(".log.old")
            if backup.exists():
                backup.unlink()
            log_file.rename(backup)


def send_alert(message):
    """Send alert to n8n/webhook"""
    try:
        requests.post(
            "https://n8n.aitradepulse.com/webhook/cs-events",
            json={
                "event": "system_alert",
                "message": message,
                "timestamp": datetime.now().isoformat(),
            },
            timeout=5,
        )
    except:
        pass


def main():
    """Main health check loop"""
    log("🚀 Health Monitor started")

    failure_counts = {
        "webhook": 0,
        "waha": 0,
        "tunnel": 0,
        "database": 0,
    }

    while True:
        try:
            # Check all services
            checks = {
                "webhook": check_webhook_server(),
                "waha": check_waha(),
                "tunnel": check_cloudflare_tunnel(),
                "database": check_database(),
            }

            # Update failure counts and recover
            for service, is_healthy in checks.items():
                if is_healthy:
                    if failure_counts[service] > 0:
                        log(f"✅ {service} is back online")
                        failure_counts[service] = 0
                else:
                    failure_counts[service] += 1
                    log(f"⚠️ {service} failed (count: {failure_counts[service]})")

                    # Auto-recover after 3 failures
                    if failure_counts[service] >= 3:
                        if service == "webhook":
                            restart_webhook_server()
                            failure_counts[service] = 0
                            failure_counts[service] = 0
                        elif service == "tunnel":
                            subprocess.run(
                                ["sudo", "systemctl", "restart", "cloudflared"],
                                capture_output=True,
                            )
                            failure_counts[service] = 0
                        elif service == "waha":
                            send_alert("WAHA service down - manual intervention needed")

            # Check for stuck conversations
            stuck = check_stuck_conversations()
            if stuck > 0:
                log(f"⚠️ Found {stuck} stuck conversations")
                clear_duplicate_messages()

            # Check disk space
            if not check_disk_space():
                log("⚠️ Disk space low - rotating logs")
                rotate_logs()

            # Rotate logs every hour
            if datetime.now().minute == 0:
                rotate_logs()

            # Sleep before next check
            time.sleep(30)

        except Exception as e:
            log(f"❌ Monitor error: {e}")
            time.sleep(30)


if __name__ == "__main__":
    main()
