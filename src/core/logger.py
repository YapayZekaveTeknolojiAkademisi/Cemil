import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime

# Slack botuna özel ASCII ikonlar ve renkler
LOG_ICONS = {
    "INFO": "[i] ",
    "SUCCESS": "[+] ",
    "WARNING": "[!] ",
    "ERROR": "[X] ",
    "CRITICAL": "[!!!]",
    "COMMAND": "[>] ",
    "MATCH": "[<>]",
    "POLL": "[?] "
}

class SlackBotFormatter(logging.Formatter):
    """
    Slack Botu için özel olarak tasarlanmış terminal log formatlayıcı.
    Kullanıcı ID'si, Komut ve Mesajı şık bir şekilde ayırır.
    """
    
    blue = "\x1b[38;5;39m"
    green = "\x1b[32m"
    yellow = "\x1b[33m"
    red = "\x1b[31m"
    magenta = "\x1b[35m"
    cyan = "\x1b[36m"
    white = "\x1b[37m"
    bold = "\x1b[1m"
    reset = "\x1b[0m"

    def format(self, record):
        # Zaman damgasını özelleştir
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        
        # Log seviyesine göre renk ve ikon seç
        level_name = record.levelname
        icon = LOG_ICONS.get(level_name, "[*] ")
        
        level_color = self.white
        if record.levelno == logging.INFO: level_color = self.green
        elif record.levelno == logging.WARNING: level_color = self.yellow
        elif record.levelno == logging.ERROR: level_color = self.red
        elif record.levelno >= logging.CRITICAL: level_color = self.bold + self.red

        # Log kaydındaki ek bilgileri ayrıştır (extra={'user': '...', 'cmd': '...'})
        user_info = f"{self.cyan}[{record.__dict__.get('user', 'SYSTEM')}] {self.reset}"
        cmd_info = f"{self.magenta}{record.__dict__.get('cmd', '')} {self.reset}" if record.__dict__.get('cmd') else ""
        
        # Ana mesaj formatı
        formatted_msg = f"{self.white}{timestamp}{self.reset} | {level_color}{icon}{level_name:<8}{self.reset} | {user_info}{cmd_info}{record.getMessage()}"
        
        # Exception varsa ekle
        if record.exc_info:
            formatted_msg += "\n" + self.formatException(record.exc_info)
            
        return formatted_msg

class CemilLogger(logging.Logger):
    """
    Slack Botuna özel metodları olan genişletilmiş Logger sınıfı.
    """
    def slack_command(self, user_id, command, message, level=logging.INFO):
        self.log(level, message, extra={"user": user_id, "cmd": f"/{command} | "})

    def slack_match(self, user1, user2, status="SUCCESS"):
        icon = LOG_ICONS["MATCH"]
        msg = f"{icon} Eşleşme: {user1} & {user2}"
        self.info(msg, extra={"user": "MATCH_ENGINE"})

def setup_logger(name="CemilBot", log_file="logs/cemil_detailed.log"):
    """
    Merkezi logger kurulumu.
    """
    # Klasör kontrolü
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Logger sınıfını değiştir
    logging.setLoggerClass(CemilLogger)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Temizleme (Handlerların mükerrer eklenmesini önler)
    if logger.hasHandlers():
        logger.handlers.clear()

    # 1. Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(SlackBotFormatter())
    logger.addHandler(console_handler)

    # 2. Rotating File Handler (JSON veya Yapısal format için uygun)
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | [%(user)s] [%(cmd)s] %(message)s",
        datefmt='%Y-%m-%d %H:%M:%S',
        defaults={"user": "SYSTEM", "cmd": "N/A"}
    )
    file_handler = RotatingFileHandler(
        log_file, 
        maxBytes=10*1024*1024, # 10MB
        backupCount=10,
        encoding="utf-8"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    return logger

# Singleton instance
logger = setup_logger()
