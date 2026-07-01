#!/usr/bin/env python3
"""
Wablas connection diagnostic.

Usage:
    python test_wablas.py              # checks creds + device connection (no message sent)
    python test_wablas.py 6281234567890   # also sends a real test message to that number
"""
import asyncio
import json
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://sby.wablas.com"


def _fmt(data) -> str:
    try:
        return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception:
        return str(data)


async def check_device(client: httpx.AsyncClient, headers: dict) -> bool:
    """Hit device info endpoint — pure connection test, sends nothing."""
    url = f"{BASE_URL}/api/device/info"
    print(f"\n[2] Device status  →  GET {url}")
    try:
        resp = await client.get(url, headers=headers)
        print(f"    HTTP {resp.status_code}")
        try:
            data = resp.json()
            print(f"    {_fmt(data)}")
        except Exception:
            print(f"    Non-JSON: {resp.text[:300]}")
            return False
        if resp.is_success and data.get("status") in (True, "true", "success"):
            print("    OK — device reachable")
            return True
        print("    FAIL — check token / device connected in Wablas dashboard")
        return False
    except httpx.TimeoutException:
        print("    FAIL — timeout after 15s (network / firewall / wrong domain)")
        return False
    except Exception as e:
        print(f"    FAIL — {e}")
        return False


async def send_test(client: httpx.AsyncClient, headers: dict, phone: str) -> bool:
    url = f"{BASE_URL}/api/send-message"
    payload = {"phone": phone, "message": "Test message from diagnostic script"}
    print(f"\n[3] Send test      →  POST {url}  (phone={phone})")
    try:
        resp = await client.post(url, headers=headers, json=payload)
        print(f"    HTTP {resp.status_code}")
        try:
            data = resp.json()
            print(f"    {_fmt(data)}")
        except Exception:
            print(f"    Non-JSON: {resp.text[:300]}")
            return False
        if resp.is_success and data.get("status") == "success":
            print("    OK — message sent")
            return True
        print("    FAIL — message not sent")
        return False
    except Exception as e:
        print(f"    FAIL — {e}")
        return False


async def main():
    api_key = os.getenv("WABLASS_API_KEY")
    secret_key = os.getenv("WABLASS_WEBHOOK_SECRET")

    print("[1] Credentials")
    if not api_key or not secret_key:
        missing = [n for n, v in (("WABLASS_API_KEY", api_key),
                                  ("WABLASS_WEBHOOK_SECRET", secret_key)) if not v]
        print(f"    FAIL — missing in .env: {', '.join(missing)}")
        sys.exit(1)
    print(f"    WABLASS_API_KEY        = {api_key[:6]}...{api_key[-4:]} (len {len(api_key)})")
    print(f"    WABLASS_WEBHOOK_SECRET = {secret_key[:2]}...{secret_key[-2:]} (len {len(secret_key)})")

    headers = {"Authorization": f"{api_key}.{secret_key}"}
    phone = sys.argv[1] if len(sys.argv) > 1 else None

    async with httpx.AsyncClient(timeout=15) as client:
        ok = await check_device(client, headers)
        if phone:
            ok = await send_test(client, headers, phone) and ok
        else:
            print("\n[3] Send test      →  skipped (pass a phone number to send:"
                  " python test_wablas.py 628xxxx)")

    print("\n" + ("=== ALL OK ===" if ok else "=== FAILED — see above ==="))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
