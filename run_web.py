#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Web 服务启动脚本。在项目根目录执行: python run_web.py
同事通过 IP 访问时，若需使用「选择目录」上传，请用 HTTPS: python run_web.py --https
"""
import argparse
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)
os.environ["PYTHONPATH"] = _ROOT + os.pathsep + os.environ.get("PYTHONPATH", "")
os.chdir(_ROOT)

_CERTS_DIR = os.path.join(_ROOT, ".certs")
_KEY_FILE = os.path.join(_CERTS_DIR, "key.pem")
_CERT_FILE = os.path.join(_CERTS_DIR, "cert.pem")


def _print_lan_urls(port=8000, use_https=False):
    import socket
    scheme = "https" if use_https else "http"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        print("\n  同事访问地址: %s://%s:%s  （HTTPS 下「选择目录」可用）\n" % (scheme, ip, port))
    except Exception:
        pass
    print("  本机访问: %s://127.0.0.1:%s\n" % (scheme, port))


def _ensure_self_signed_cert():
    """若 .certs 下无证书则生成自签名证书（需 pip install cryptography）。"""
    if os.path.isfile(_KEY_FILE) and os.path.isfile(_CERT_FILE):
        return _KEY_FILE, _CERT_FILE
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        import datetime
    except ImportError:
        print("HTTPS 需要自签名证书，请先安装: pip install cryptography")
        sys.exit(1)
    os.makedirs(_CERTS_DIR, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "EduFlow LAN")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow() - datetime.timedelta(days=1))
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    with open(_KEY_FILE, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    with open(_CERT_FILE, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    print("已生成自签名证书: %s" % _CERTS_DIR)
    return _KEY_FILE, _CERT_FILE


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="启动 EduFlow Web 服务")
    p.add_argument("--https", action="store_true", help="使用 HTTPS，同事通过 IP 访问时「选择目录」可用")
    args = p.parse_args()
    use_https = args.https
    port = 8000
    if use_https:
        _ensure_self_signed_cert()
        _print_lan_urls(port, use_https=True)
        import uvicorn
        uvicorn.run(
            "api.app:app",
            host="0.0.0.0",
            port=port,
            reload=True,
            ssl_keyfile=_KEY_FILE,
            ssl_certfile=_CERT_FILE,
        )
    else:
        _print_lan_urls(port)
        import uvicorn
        uvicorn.run(
            "api.app:app",
            host="0.0.0.0",
            port=port,
            reload=True,
        )
