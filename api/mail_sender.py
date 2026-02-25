# -*- coding: utf-8 -*-
"""
通过 SMTP 发邮件。从环境变量读取配置；未配置则不发送。
"""
import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr

logger = logging.getLogger(__name__)


def _smtp_config() -> dict | None:
    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        return None
    port_str = os.getenv("SMTP_PORT", "465").strip()
    try:
        port = int(port_str)
    except ValueError:
        port = 465
    use_ssl = os.getenv("SMTP_USE_SSL", "1").strip().lower() in ("1", "true", "yes")
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    mail_from = os.getenv("MAIL_FROM", "").strip() or user
    if not user or not password:
        return None
    return {
        "host": host,
        "port": port,
        "use_ssl": use_ssl,
        "user": user,
        "password": password,
        "mail_from": mail_from,
    }


def send_email(to_email: str, subject: str, body_text: str) -> bool:
    """
    发一封纯文本邮件。to_email 为收件人地址。
    若未配置 SMTP 或发送失败返回 False，成功返回 True。
    """
    cfg = _smtp_config()
    if not cfg:
        return False
    to_email = (to_email or "").strip().lower()
    if not to_email or "@" not in to_email:
        return False
    try:
        msg = MIMEText(body_text, "plain", "utf-8")
        msg["Subject"] = subject
        # MAIL_FROM 可为 "EduFlow <xxx@xx.com>" 或直接 "xxx@xx.com"
        if "<" in cfg["mail_from"] and ">" in cfg["mail_from"]:
            name = cfg["mail_from"].split("<")[0].strip()
            addr = cfg["mail_from"].split("<")[1].split(">")[0].strip()
            msg["From"] = formataddr((name or "EduFlow", addr))
        else:
            msg["From"] = cfg["mail_from"]
        msg["To"] = to_email
        if cfg["use_ssl"]:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"]) as smtp:
                smtp.login(cfg["user"], cfg["password"])
                smtp.sendmail(cfg["user"], to_email, msg.as_string())
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"]) as smtp:
                smtp.starttls()
                smtp.login(cfg["user"], cfg["password"])
                smtp.sendmail(cfg["user"], to_email, msg.as_string())
        return True
    except Exception as e:
        logger.warning("发送邮件失败: %s", e)
        return False


def send_password_reset_email(to_email: str, reset_url: str) -> bool:
    """发送找回密码邮件，内容为重置链接。"""
    subject = "EduFlow 找回密码"
    body = f"""您好，

您正在申请重置 EduFlow 账户密码。请点击下方链接设置新密码（链接 1 小时内有效）：

{reset_url}

如非本人操作，请忽略此邮件。
"""
    return send_email(to_email, subject, body)
